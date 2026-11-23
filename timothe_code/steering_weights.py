"""Weight steering of a small local model: can editing its weights move its votes left or right?

Votes are measured as the probabilities of POUR / CONTRE / ABSTENTION as first answer token, with the same
prompt as the API models (prompt_v1); position = p(POUR) - p(CONTRE). Two experiments:

  run         Training-free rank-1 edit. A left-right direction (difference of activations between a
              left-wing and a right-wing persona, or between left and right statements) is added to one
              layer, either at inference ("hook") or written into the layer's MLP output matrix ("edit":
              dW = direction u^T, u fitted in closed form so that u . activation ~ 1 on every token).
  arithmetic  Weight arithmetic (Fierro & Roger, 2026). Two small low-rank adapters are trained on short
              texts put in the voting prompt: "left" votes for the left-wing ones and against the
              right-wing ones, "right" the reverse. The texts are policy proposals written for the
              experiment (steering_statements.json) or, with --train titles, the titles of real private
              members' bills labelled by the camp of their author (steering_titles.json). The model is
              then steered with W + coef * (dW_left - dW_right), and evaluated on held-out texts and on
              the real bills.

Usage, from the repository root (needs a GPU with about 12 GB):
    python timothe_code/steering_weights.py probe        # baseline votes and answer format of the local model
    python timothe_code/steering_weights.py sweep        # run: choose the layer (activation steering on a subset)
    python timothe_code/steering_weights.py run          # -> results/results-<datetime>_weights/
    python timothe_code/steering_weights.py arithmetic   # -> results/results-<datetime>_weights/
    python timothe_code/steering_weights.py arithmetic --train titles
    python timothe_code/steering_weights.py extract      # rebuild steering_titles.json from dataset/data/
"""

import argparse
import collections
import json
import logging
import os
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis as an  # noqa: E402
import steering_prompt as sp  # noqa: E402
import vote_pipeline as vp  # noqa: E402

logger = logging.getLogger(__name__)
ds = vp.ds

MODEL_ID = "Qwen/Qwen3-4B"
MODEL_NAME = "local/Qwen3-4B"
VARIANT = "prompt_v1"
STATEMENTS_FILE = os.path.join(vp.HERE, "steering_statements.json")
STATEMENT_QUESTION = "Donne ton opinion politique en une phrase."
MAX_TEXT_CHARS = 30000
LEGISLATURE = 17
VOTE_WORDS = {"for": "POUR", "against": "CONTRE", "abstain": "ABSTENTION"}
SWEEP_LAYERS = (6, 10, 14, 18, 22, 26)
SWEEP_COEFS = (0.15, 0.4)
MAX_FIT_CHARS = 12000
PERSONA_LEFT, PERSONA_RIGHT = "persona_gauche", "persona_droite"
RUN_COEFS = (-0.3, -0.2, -0.1, -0.05, 0.05, 0.1, 0.2, 0.3)
RIDGE = 1e-2
N_CALIBRATION_TOKENS = 4000
SEED = 0
REPORT_FILE = "weights_report.md"
PLOT_FILE = "weights_dose_response.png"
EDIT_FILE = "weight_edit.pt"
SWEEP_FILE = os.path.join(vp.RESULTS_ROOT, "weights_sweep.json")
MIN_MASS = 0.5  # below this, the model no longer answers with a vote
N_CALIBRATION_BILLS = 12
# weight arithmetic
ADAPTER_MODULES = ("q_proj", "v_proj")
ADAPTER_RANK, ADAPTER_ALPHA = 8, 16
ADAPTER_LR = 2e-4
ADAPTER_SCHEDULE = {"proposals": (12, 6), "titles": (8, 4)}  # training texts: (epochs, batch size)
CAMPS = ("left", "right")
PROPOSAL_TITLE = "Proposition"
N_HELD_OUT_PAIRS = 6
TITLES_FILE = os.path.join(vp.HERE, "steering_titles.json")
YANNIS_DATA = os.path.join(vp.ROOT, "dataset", "data")
PRIVATE_BILL_PROCEDURE = "Proposition de loi"
TITLE_PREFIX = "proposition de loi : "
TITLE_TRAIN_LEGISLATURES = (15, 16)
MAX_TITLE_CHARS = 200
N_HELD_OUT_TITLES = 150
SCORE_BATCH = 32
TRAINED_ON = {"proposals": "short policy proposals written for the experiment",
              "titles": "titles of real private members' bills of earlier legislatures, left-wing or right-wing "
                        "according to the group that tabled them"}
ARITH_COEFS = (-1.5, -1.0, -0.5, -0.25, 0.25, 0.5, 1.0, 1.5)
ADAPTERS_FILE = "weight_adapters.pt"
ARITH_REPORT, ARITH_PLOT = "arithmetic_report.md", "arithmetic_dose_response.png"


# ---------------------------------------------------------------- model and votes

def load_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    return tok, model


def chat_text(tok, messages, prefill=""):
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    return text + prefill


def vote_token_ids(tok):
    """{label: ids of every token that can start the vote word}, e.g. "P", "PO", "POUR" for POUR.

    The three words start with different letters, so the sets are disjoint.
    """
    ids = {label: [] for label in VOTE_WORDS}
    for token_id in range(len(tok)):
        piece = tok.decode([token_id])
        for label, word in VOTE_WORDS.items():
            if piece and word.startswith(piece):
                ids[label].append(token_id)
    return ids


@torch.no_grad()
def next_token_probs(tok, model, text):
    """Probabilities of the next token. Only the last position goes through the output layer (memory)."""
    enc = tok(text, return_tensors="pt").to(model.device)
    hidden = model.model(**enc).last_hidden_state[0, -1]
    return torch.softmax(model.lm_head(hidden).float(), -1)


def vote_probs(tok, model, text, token_ids):
    """({label: probability renormalised over the three votes}, total probability of the three votes)."""
    probs = next_token_probs(tok, model, text)
    raw = {label: float(probs[ids].sum()) for label, ids in token_ids.items()}
    mass = sum(raw.values())
    return {label: p / mass for label, p in raw.items()}, mass


def bills():
    """Divisive bills short enough for the local model, with their chat prompts built by the pipeline."""
    return [dp for dp in ds.divisive(ds.load(legislature=LEGISLATURE)) if dp["text_content"]["voted_text_chars"] <= MAX_TEXT_CHARS]


def evaluate(tok, model, datapoints, prompts, token_ids, prefill, title_only=False):
    """{bill id: {"probs", "mass", "position"}} for the model in its current state."""
    out = {}
    for dp in datapoints:
        if title_only:
            text = short_text(tok, prompts, dp["text_content"]["title"], "", prefill)
        else:
            text = chat_text(tok, vp.build_messages(dp, VARIANT, prompts), prefill)
        probs, mass = vote_probs(tok, model, text, token_ids)
        out[dp["id"]] = {"probs": probs, "mass": mass, "position": probs["for"] - probs["against"]}
    return out


def alignment(result, datapoints):
    """Balanced left alignment and summary numbers of one evaluation.

    left alignment = (mean position on the bills the left supports - mean position on the bills the left
    opposes) / 2, over bills where left and right are opposed: +1 = votes like the left, -1 = like the
    right. Balanced so that a mere shift towards POUR or CONTRE leaves it unchanged.
    """
    left = {dp["id"]: sp.stance(sp.camp_position(dp, an.LEFT_GROUPS)) for dp in datapoints}
    right = {dp["id"]: sp.stance(sp.camp_position(dp, an.RIGHT_GROUPS)) for dp in datapoints}
    opposed = [i for i in left if left[i] and right[i] and left[i] != right[i]]
    sup = [result[i]["position"] for i in opposed if left[i] > 0]
    opp = [result[i]["position"] for i in opposed if left[i] < 0]
    labels = collections.Counter(max(r["probs"], key=r["probs"].get) for r in result.values())
    return {"left_alignment": (np.mean(sup) - np.mean(opp)) / 2 if sup and opp else None,
            "pos_left_bills": float(np.mean(sup)) if sup else None, "pos_right_bills": float(np.mean(opp)) if opp else None,
            "mean_position": float(np.mean([r["position"] for r in result.values()])),
            "mass": float(np.mean([r["mass"] for r in result.values()])),
            "n_opposed": len(opposed), "n_left_bills": len(sup), "n_right_bills": len(opp), "labels": dict(labels)}


# ---------------------------------------------------------------- direction

@torch.no_grad()
def statement_states(tok, model, statement):
    """Residual stream after each layer, averaged over the tokens of one statement: [n_layers, hidden]."""
    messages = [{"role": "user", "content": STATEMENT_QUESTION}, {"role": "assistant", "content": statement}]
    text = tok.apply_chat_template(messages, tokenize=False, continue_final_message=True, enable_thinking=False)
    n = len(tok.encode(statement, add_special_tokens=False))
    enc = tok(text, return_tensors="pt").to(model.device)
    hs = model(**enc, output_hidden_states=True).hidden_states[1:]
    return torch.stack([h[0, -n:].float().mean(0) for h in hs])


@torch.no_grad()
def decision_states(tok, model, text):
    """Residual stream after each layer at the last position, where the vote is decided: [n_layers, hidden]."""
    enc = tok(text, return_tensors="pt").to(model.device)
    hs = model.model(**enc, output_hidden_states=True).hidden_states[1:]
    return torch.stack([h[0, -1].float() for h in hs])


def fit_bills(evaluated):
    """Bills used to compute directions and calibrate edits: never the evaluated ones."""
    skip = {dp["id"] for dp in evaluated}
    return [dp for dp in ds.load(legislature=LEGISLATURE) if dp["id"] not in skip and dp["text_content"]["voted_text_chars"] <= MAX_FIT_CHARS]


def directions(ctx, source):
    """(direction [n_layers, hidden] = mean left - mean right, mean residual norm per layer).

    source "statements": left-wing vs right-wing statements, averaged over their tokens.
    source "persona": the same bill prompt with a left-wing vs a right-wing persona as system message,
    at the position where the vote is decided, over bills that are not evaluated.
    """
    tok, model, datapoints, prompts, token_ids, prefill = ctx
    if source == "statements":
        with open(STATEMENTS_FILE, encoding="utf-8") as f:
            pairs = json.load(f)["pairs"]
        left = torch.stack([statement_states(tok, model, a) for a, _ in pairs])
        right = torch.stack([statement_states(tok, model, b) for _, b in pairs])
    else:
        fit = fit_bills(datapoints)
        left = torch.stack([decision_states(tok, model, chat_text(tok, vp.build_messages(dp, PERSONA_LEFT, prompts), prefill)) for dp in fit])
        right = torch.stack([decision_states(tok, model, chat_text(tok, vp.build_messages(dp, PERSONA_RIGHT, prompts), prefill)) for dp in fit])
        logger.info("persona direction fitted on %d bills that are not evaluated", len(fit))
    norms = torch.cat([left, right]).norm(dim=-1).mean(0)
    return left.mean(0) - right.mean(0), norms


def scaled(direction, norms, layer, coef):
    """Steering vector at `layer`: its norm is coef x the typical residual norm; coef > 0 points left."""
    v = direction[layer]
    return v / v.norm() * norms[layer] * coef


# ---------------------------------------------------------------- steering: hook and weight edit

class Hook:
    """Activation steering: adds a vector to the output of one layer, at every position."""

    def __init__(self, model, layer, vector):
        self.vector = vector.to(model.dtype)
        self.handle = model.model.layers[layer].register_forward_hook(self)

    def __call__(self, module, args, output):
        if isinstance(output, tuple):
            return (output[0] + self.vector,) + tuple(output[1:])
        return output + self.vector

    def remove(self):
        self.handle.remove()


class Rank1Edit(torch.nn.Module):
    """A linear layer with the rank-1 weight change dW = v u^T: y = W x + v (u . x).

    Kept factorised and computed in float32, because the model's weights are in bfloat16, too coarse to
    absorb the small entries of dW. merged_weight() returns the edited matrix W + v u^T.
    """

    def __init__(self, linear, v, u):
        super().__init__()
        self.linear, self.v, self.u = linear, v.float(), u.float()

    def forward(self, x):
        return self.linear(x) + ((x.float() @ self.u).unsqueeze(-1) * self.v).to(x.dtype)

    def merged_weight(self):
        return self.linear.weight.float() + torch.outer(self.v, self.u)


@torch.no_grad()
def mlp_hidden(tok, model, layer, texts, max_tokens=N_CALIBRATION_TOKENS):
    """Inputs of the layer's MLP output matrix (down_proj) on the tokens of `texts`: [n_tokens, d_mlp]."""
    rows = []
    handle = model.model.layers[layer].mlp.down_proj.register_forward_pre_hook(
        lambda module, args: rows.append(args[0][0].float().cpu()))
    for text in texts:
        model.model(**tok(text, return_tensors="pt", truncation=True, max_length=1024).to(model.device))
    handle.remove()
    acts = torch.cat(rows)
    idx = torch.randperm(len(acts), generator=torch.Generator().manual_seed(SEED))[:max_tokens]
    return acts[idx]


def fit_constant_reader(acts, ridge=RIDGE):
    """u minimising |A u - 1|^2 + ridge * |u|^2 (dual form): u . a ~ 1 for a typical activation a."""
    A = acts.double()
    K = A @ A.T
    lam = ridge * K.diagonal().mean()
    alpha = torch.linalg.solve(K + lam * torch.eye(len(A), dtype=A.dtype), torch.ones(len(A), dtype=A.dtype))
    return (A.T @ alpha).float()


def apply_edit(model, layer, vector, u):
    mlp = model.model.layers[layer].mlp
    original = mlp.down_proj
    mlp.down_proj = Rank1Edit(original, vector.to(model.device), u.to(model.device))
    return original


def remove_edit(model, layer, original):
    model.model.layers[layer].mlp.down_proj = original


# ---------------------------------------------------------------- steps

def probe(tok, model, datapoints, prompts):
    """Print what the model answers first, to choose the prefill, and its baseline alignment."""
    for dp in datapoints[:4]:
        text = chat_text(tok, vp.build_messages(dp, VARIANT, prompts))
        enc = tok(text, return_tensors="pt").to(model.device)
        probs = next_token_probs(tok, model, text)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=40, do_sample=False)
        top = torch.topk(probs, 6)
        print("%s (%d tokens) top: %s" % (dp["id"], enc.input_ids.shape[1],
              [(tok.decode(i), round(float(p), 3)) for p, i in zip(top.values, top.indices)]))
        print("   ->", repr(tok.decode(gen[0, enc.input_ids.shape[1]:], skip_special_tokens=True)))


def opposed_only(datapoints):
    keep = []
    for dp in datapoints:
        l, r = sp.stance(sp.camp_position(dp, an.LEFT_GROUPS)), sp.stance(sp.camp_position(dp, an.RIGHT_GROUPS))
        if l and r and l != r:
            keep.append(dp)
    return keep


def sweep(ctx, source):
    """Activation steering at several layers, on the opposed bills: which layer moves the alignment most?"""
    tok, model, datapoints, prompts, token_ids, prefill = ctx
    subset = opposed_only(datapoints)
    direction, norms = directions(ctx, source)
    for name in (PERSONA_LEFT, PERSONA_RIGHT):  # reference: steering the same model through its prompt
        res = {dp["id"]: None for dp in subset}
        for dp in subset:
            probs, mass = vote_probs(tok, model, chat_text(tok, vp.build_messages(dp, name, prompts), prefill), token_ids)
            res[dp["id"]] = {"probs": probs, "mass": mass, "position": probs["for"] - probs["against"]}
        logger.info("prompt reference %s: left alignment %+.3f", name, alignment(res, subset)["left_alignment"])
    base = alignment(evaluate(tok, model, subset, prompts, token_ids, prefill), subset)
    logger.info("baseline on %d opposed bills: left alignment %+.3f, mass %.2f", len(subset), base["left_alignment"], base["mass"])
    rows = []
    for layer, coef in [(l, c) for c in SWEEP_COEFS for l in SWEEP_LAYERS]:
        res = {}
        for sign in (+1, -1):
            hook = Hook(model, layer, scaled(direction, norms, layer, sign * coef))
            res[sign] = alignment(evaluate(tok, model, subset, prompts, token_ids, prefill), subset)
            hook.remove()
        effect = res[+1]["left_alignment"] - res[-1]["left_alignment"]
        rows.append({"layer": layer, "coef": coef, "left": res[+1]["left_alignment"], "right": res[-1]["left_alignment"], "effect": effect,
                     "mass_left": res[+1]["mass"], "mass_right": res[-1]["mass"]})
        logger.info("layer %2d: coef +%.2f -> %+.3f (mass %.2f) | coef -%.2f -> %+.3f (mass %.2f) | effect %+.3f",
                    layer, coef, res[+1]["left_alignment"], res[+1]["mass"], coef,
                    res[-1]["left_alignment"], res[-1]["mass"], effect)
    valid = [r for r in rows if min(r["mass_left"], r["mass_right"]) >= MIN_MASS] or rows
    best = max(valid, key=lambda r: r["effect"])
    os.makedirs(vp.RESULTS_ROOT, exist_ok=True)
    with open(SWEEP_FILE, "w", encoding="utf-8") as f:
        json.dump({"model": MODEL_ID, "direction": source, "baseline": base["left_alignment"], "rows": rows,
                   "best_layer": best["layer"]}, f, indent=1)
    logger.info("best layer: %d (written to %s)", best["layer"], SWEEP_FILE)


def calibration_texts(tok, prompts, evaluated):
    """Statements and the start of bills that are not evaluated: tokens on which the reader u is fitted."""
    with open(STATEMENTS_FILE, encoding="utf-8") as f:
        texts = [s for pair in json.load(f)["pairs"] for s in pair]
    return texts + [chat_text(tok, vp.build_messages(dp, VARIANT, prompts)) for dp in fit_bills(evaluated)[:N_CALIBRATION_BILLS]]


def run(ctx, layer, source):
    """Dose-response of activation steering (hook) and of the weight edit, plus a random-direction control."""
    tok, model, datapoints, prompts, token_ids, prefill = ctx
    direction, norms = directions(ctx, source)
    acts = mlp_hidden(tok, model, layer, calibration_texts(tok, prompts, datapoints))
    n_fit = int(0.8 * len(acts))
    u = fit_constant_reader(acts[:n_fit])
    held = acts[n_fit:] @ u
    reader = {"mean": float(held.mean()), "std": float(held.std()), "n_fit": n_fit, "n_heldout": len(held)}
    logger.info("layer %d: reader u fitted on %d tokens; on %d held-out tokens u.a = %.2f +/- %.2f (target 1)",
                layer, n_fit, len(held), reader["mean"], reader["std"])
    rng = torch.Generator().manual_seed(SEED)
    random_dir = torch.randn(direction.shape[1], generator=rng).to(direction.device)
    random_dir = random_dir - (random_dir @ direction[layer]) / direction[layer].norm() ** 2 * direction[layer]

    evals = {"baseline": evaluate(tok, model, datapoints, prompts, token_ids, prefill)}
    logger.info("baseline: %s", alignment(evals["baseline"], datapoints))
    for coef in RUN_COEFS:
        vector = scaled(direction, norms, layer, coef)
        hook = Hook(model, layer, vector)
        evals["hook_%+.2f" % coef] = evaluate(tok, model, datapoints, prompts, token_ids, prefill)
        hook.remove()
        original = apply_edit(model, layer, vector, u)
        evals["edit_%+.2f" % coef] = evaluate(tok, model, datapoints, prompts, token_ids, prefill)
        remove_edit(model, layer, original)
        rv = random_dir / random_dir.norm() * norms[layer] * coef
        original = apply_edit(model, layer, rv, u)
        evals["random_%+.2f" % coef] = evaluate(tok, model, datapoints, prompts, token_ids, prefill)
        remove_edit(model, layer, original)
        logger.info("coef %+.2f: hook %+.3f | edit %+.3f | random edit %+.3f (left alignment)", coef,
                    *(alignment(evals["%s_%+.2f" % (k, coef)], datapoints)["left_alignment"] for k in ("hook", "edit", "random")))

    run_dir = vp.new_run_dir("_weights")
    strongest = max(RUN_COEFS, key=abs)
    torch.save({"model": MODEL_ID, "layer": layer, "module": "model.layers.%d.mlp.down_proj" % layer,
                "direction_unit": (direction[layer] / direction[layer].norm()).cpu(), "residual_norm": float(norms[layer]),
                "u": u.cpu(), "coefs": RUN_COEFS,
                "how_to": "dW = coef * residual_norm * outer(direction_unit, u); W_new = W + dW (coef > 0 = left)"},
               os.path.join(run_dir, EDIT_FILE))
    write_outputs(run_dir, evals, datapoints, prompts, tok, layer, reader, prefill, strongest)
    logger.info("results in %s", run_dir)


# ---------------------------------------------------------------- weight arithmetic

class Adapters(torch.nn.Module):
    """A linear layer plus named low-rank changes: y = W x + sum_n coef_n * scale * B_n A_n x.

    Computed in float32 next to the frozen bfloat16 weights. With coefs {"left": c, "right": -c} the layer
    carries the weight-arithmetic edit W + c * (dW_left - dW_right).
    """

    def __init__(self, linear):
        super().__init__()
        self.linear, self.factors, self.coefs = linear, {}, {}

    def add(self, name):
        device = self.linear.weight.device
        a = torch.nn.Parameter(torch.randn(ADAPTER_RANK, self.linear.in_features, device=device) * 0.01)
        b = torch.nn.Parameter(torch.zeros(self.linear.out_features, ADAPTER_RANK, device=device))
        self.factors[name], self.coefs[name] = (a, b), 0.0
        return [a, b]

    def forward(self, x):
        y = self.linear(x)
        for name, (a, b) in self.factors.items():
            coef = self.coefs[name]
            if coef != 0.0:
                y = y + (((x.float() @ a.T) @ b.T) * (coef * ADAPTER_ALPHA / ADAPTER_RANK)).to(y.dtype)
        return y


def install_adapters(model):
    for p in model.parameters():
        p.requires_grad_(False)
    modules = []
    for layer in model.model.layers:
        for name in ADAPTER_MODULES:
            wrapped = Adapters(getattr(layer.self_attn, name))
            setattr(layer.self_attn, name, wrapped)
            modules.append(wrapped)
    return modules


def set_coefs(modules, **coefs):
    for m in modules:
        for name in m.coefs:
            m.coefs[name] = coefs.get(name, 0.0)


def short_text(tok, prompts, title, text, prefill):
    """A short text (a policy proposal, or nothing after a bill's title) in the same voting prompt as the bills."""
    user = prompts["variants"][VARIANT]["template"].format(title=title, voted_text=text, question="")
    return chat_text(tok, [{"role": "user", "content": user}], prefill)


def as_list(x):
    return x if isinstance(x, list) else [] if x is None else [x]


def first_date(stage):
    if stage.get("dateActe"):
        return stage["dateActe"][:10]
    steps = as_list((stage.get("actesLegislatifs") or {}).get("acteLegislatif"))
    return next((d for d in map(first_date, steps) if d), None)


def extract_titles(data_dir=YANNIS_DATA, out_file=TITLES_FILE):
    """Write the private members' bills first tabled at the Assemblee whose first author sat in a left or right group.

    One row per dossier: legislature, short title, the author's group when the bill was tabled, and its camp.
    """
    with open(os.path.join(data_dir, "dataset", "groupes.json"), encoding="utf-8") as f:
        family = {g["sigle"]: g["famille"] for g in json.load(f)["groupes"].values()}
    with open(os.path.join(data_dir, "dataset", "deputes.json"), encoding="utf-8") as f:
        deputies = json.load(f)
    rows = {}
    dossiers = os.path.join(data_dir, "sources", "dossiers")
    for leg in sorted(os.listdir(dossiers)):
        folder = os.path.join(dossiers, leg, "dossierParlementaire")
        for name in sorted(os.listdir(folder)):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                d = json.load(f)
            d = d.get("dossierParlementaire", d)
            stages = as_list((d.get("actesLegislatifs") or {}).get("acteLegislatif"))
            authors = as_list(((d.get("initiateur") or {}).get("acteurs") or {}).get("acteur"))
            procedure = (d.get("procedureParlementaire") or {}).get("libelle") or ""
            if not (procedure.startswith(PRIVATE_BILL_PROCEDURE) and authors and stages
                    and (stages[0].get("codeActe") or "").startswith("AN")):
                continue
            date, groups = first_date(stages[0]), deputies.get(authors[0]["acteurRef"], {}).get("groupes", {})
            group = next((g for g, (start, end) in groups.items() if date and start <= date <= (end or "9999")), None)
            camp = "left" if family.get(group) in an.LEFT_FAMILIES else "right" if family.get(group) in an.RIGHT_FAMILIES else None
            if camp:
                rows[d["uid"]] = {"dossier": d["uid"], "legislature": int(d["legislature"]),
                                  "title": d["titreDossier"]["titre"], "group": group, "camp": camp}
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(sorted(rows.values(), key=lambda r: (r["legislature"], r["dossier"])), f, ensure_ascii=False, indent=0)
    logger.info("%d bills written to %s: %s", len(rows), out_file,
                dict(collections.Counter((r["legislature"], r["camp"]) for r in rows.values())))


def training_texts(source, tok, prompts, prefill, datapoints):
    """(texts to train on, texts held out), each {"left": [...], "right": [...]} of short voting prompts.

    proposals: the pairs of steering_statements.json, the last ones held out.
    titles: bills of the earlier legislatures to train, bills of the evaluated legislature held out; the
    dossiers of the evaluated bills are left out of both.
    """
    if source == "proposals":
        with open(STATEMENTS_FILE, encoding="utf-8") as f:
            pairs = json.load(f)["pairs"]
        texts = {"left": [short_text(tok, prompts, PROPOSAL_TITLE, a, prefill) for a, _ in pairs],
                 "right": [short_text(tok, prompts, PROPOSAL_TITLE, b, prefill) for _, b in pairs]}
        return ({c: t[:-N_HELD_OUT_PAIRS] for c, t in texts.items()}, {c: t[-N_HELD_OUT_PAIRS:] for c, t in texts.items()})
    with open(TITLES_FILE, encoding="utf-8") as f:
        rows = json.load(f)
    evaluated = {dp["text_content"]["dossier_id"] for dp in datapoints}
    rng = random.Random(SEED)

    def pool(camp, legislatures):
        return [short_text(tok, prompts, TITLE_PREFIX + r["title"], "", prefill) for r in rows
                if r["camp"] == camp and r["legislature"] in legislatures and r["dossier"] not in evaluated
                and len(r["title"]) <= MAX_TITLE_CHARS]

    train = {c: pool(c, TITLE_TRAIN_LEGISLATURES) for c in CAMPS}
    held = {c: pool(c, (LEGISLATURE,)) for c in CAMPS}
    n_train = min(len(t) for t in train.values())
    return ({c: rng.sample(t, n_train) for c, t in train.items()},
            {c: rng.sample(t, min(N_HELD_OUT_TITLES, len(t))) for c, t in held.items()})


def vote_logprobs(tok, model, texts, token_ids):
    """{label: log-probability of the vote as first answer token}, one value per text (differentiable)."""
    enc = tok(texts, return_tensors="pt", padding=True, padding_side="left").to(model.device)
    hidden = model.model(**enc).last_hidden_state[:, -1]
    logp = torch.log_softmax(model.lm_head(hidden).float(), -1)
    return {label: torch.logsumexp(logp[:, ids], -1) for label, ids in token_ids.items()}


@torch.no_grad()
def camp_score(tok, model, texts, token_ids):
    """Left score on short texts = (mean position on the left-wing ones - on the right-wing ones) / 2, with both means."""
    def mean_position(items):
        values = []
        for start in range(0, len(items), SCORE_BATCH):
            lp = vote_logprobs(tok, model, items[start:start + SCORE_BATCH], token_ids)
            values += (lp["for"].exp() - lp["against"].exp()).tolist()
        return float(np.mean(values))
    left, right = mean_position(texts["left"]), mean_position(texts["right"])
    return {"score": (left - right) / 2, "pos_left": left, "pos_right": right}


def train_adapter(tok, model, modules, name, examples, token_ids, epochs, batch_size):
    """Train the adapter `name` so that each (text, label) example gets its label as vote."""
    params = [p for m in modules for p in m.add(name)]
    set_coefs(modules, **{name: 1.0})
    optimizer = torch.optim.AdamW(params, lr=ADAPTER_LR)
    generator = torch.Generator().manual_seed(SEED)
    for epoch in range(epochs):
        order = torch.randperm(len(examples), generator=generator).tolist()
        total = 0.0
        for start in range(0, len(examples), batch_size):
            batch = [examples[i] for i in order[start:start + batch_size]]
            lp = vote_logprobs(tok, model, [t for t, _ in batch], token_ids)
            loss = -torch.stack([lp[label][k] for k, (_, label) in enumerate(batch)]).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch)
        logger.info("adapter %s, epoch %d: loss %.3f", name, epoch + 1, total / len(examples))
    for p in params:
        p.requires_grad_(False)


def arithmetic(ctx, source):
    """Train the left and right adapters, then steer with coef * (left - right): short texts and bills."""
    tok, model, datapoints, prompts, token_ids, prefill = ctx
    ids = {label: torch.tensor(v, device=model.device) for label, v in token_ids.items()}
    train, held = training_texts(source, tok, prompts, prefill, datapoints)
    logger.info("adapters trained on %s: %d texts per camp, %d held out", source, len(train["left"]), len(held["left"]))
    modules = install_adapters(model)
    for name, left_label, right_label in (("left", "for", "against"), ("right", "against", "for")):
        examples = [(t, left_label) for t in train["left"]] + [(t, right_label) for t in train["right"]]
        train_adapter(tok, model, modules, name, examples, ids, *ADAPTER_SCHEDULE[source])
    seen = {c: t[:N_HELD_OUT_TITLES] for c, t in train.items()}

    states = {"baseline": {}, "left adapter": {"left": 1.0}, "right adapter": {"right": 1.0}}
    states.update({"arith_%+.2f" % c: {"left": c, "right": -c} for c in ARITH_COEFS})
    evals, summary = {}, {}
    for key, coefs in states.items():
        set_coefs(modules, **coefs)
        evals[key] = evaluate(tok, model, datapoints, prompts, token_ids, prefill)
        by_title = alignment(evaluate(tok, model, datapoints, prompts, token_ids, prefill, title_only=True), datapoints)
        summary[key] = dict(alignment(evals[key], datapoints), title_only=by_title["left_alignment"],
                            held_out=camp_score(tok, model, held, ids), train=camp_score(tok, model, seen, ids))
        logger.info("%-14s held-out %+.2f (train %+.2f) | bills: left alignment %+.3f (title only %+.3f), mean position %+.2f, %s",
                    key, summary[key]["held_out"]["score"], summary[key]["train"]["score"], summary[key]["left_alignment"],
                    summary[key]["title_only"], summary[key]["mean_position"], summary[key]["labels"])
    set_coefs(modules)

    run_dir = vp.new_run_dir("_weights" if source == "proposals" else "_weights_%s" % source)
    torch.save({"model": MODEL_ID, "modules": ADAPTER_MODULES, "rank": ADAPTER_RANK, "scale": ADAPTER_ALPHA / ADAPTER_RANK,
                "factors": [{n: (a.detach().cpu(), b.detach().cpu()) for n, (a, b) in m.factors.items()} for m in modules],
                "how_to": "module i (layers in order, then q_proj, v_proj): W_new = W + coef * scale * (B_left A_left - B_right A_right)"},
               os.path.join(run_dir, ADAPTERS_FILE))
    arith_keys = sorted((k for k in evals if k.startswith("arith_")), key=lambda k: float(k.split("_")[1]))
    shown = [k for k in arith_keys if float(k.split("_")[1]) < 0] + ["baseline"] + [k for k in arith_keys if float(k.split("_")[1]) > 0]
    write_run_folder(run_dir, {k: evals[k] for k in shown}, datapoints, prompts, {"prefill": prefill, "method": "weight arithmetic"},
                     "WEIGHT ARITHMETIC on %s: left/right adapters trained on %s, %d divisive bills" % (MODEL_ID, source, len(datapoints)))
    with open(os.path.join(run_dir, "arithmetic_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    write_arithmetic_report(run_dir, summary, source, len(train["left"]), len(held["left"]), len(datapoints))
    plot_arithmetic(run_dir, summary)
    vp.write_report(run_dir)
    logger.info("results in %s", run_dir)


def write_arithmetic_report(run_dir, summary, source, n_train, n_held, n_bills):
    base = summary["baseline"]
    f2 = lambda x: "-" if x is None else "%+.2f" % x
    lines = ["# Weight arithmetic on %s" % MODEL_ID, "",
             "Two low-rank adapters (rank %d on the attention query and value matrices of every layer) are trained on %s: "
             "%d left-wing and %d right-wing texts, each put in the voting prompt. The left adapter votes for the left-wing "
             "ones and against the right-wing ones, the right adapter the reverse. The model is steered with "
             "W + coef x (dW_left - dW_right); coef > 0 points left." % (ADAPTER_RANK, TRAINED_ON[source], n_train, n_train), "",
             "- **held-out score** (%d left-wing and %d right-wing texts of the same kind, not used in training): (mean "
             "position on the left-wing ones - on the right-wing ones) / 2; +1 = approves the left's and rejects the "
             "right's." % (n_held, n_held),
             "- **bills: left alignment** (%d divisive bills, %d with left and right opposed): (mean position on bills the "
             "left supports - on bills it opposes) / 2. \"Title only\": the same bills without their text." % (n_bills, base["n_opposed"]),
             "- **bills: mean position**: +1 = votes for everything, -1 = against everything.", "",
             "| state | held-out score | on left-wing texts | on right-wing texts | bills, title only: left alignment "
             "| bills: left alignment | bills: mean position | bills: votes |",
             "|---|---|---|---|---|---|---|---|"]
    order = ["right adapter"] + sorted((k for k in summary if k.startswith("arith_")), key=lambda k: float(k.split("_")[1]))
    order = [k for k in order if not k.startswith("arith_+")] + ["baseline"] + [k for k in order if k.startswith("arith_+")] + ["left adapter"]
    for key in order:
        r = summary[key]
        name = key if not key.startswith("arith_") else "coef %s" % key.split("_")[1]
        lines.append("| %s | **%s** | %s | %s | %s | **%s** | %s | %s |" % (
            name, f2(r["held_out"]["score"]), f2(r["held_out"]["pos_left"]), f2(r["held_out"]["pos_right"]),
            f2(r["title_only"]), f2(r["left_alignment"]), f2(r["mean_position"]), r["labels"]))
    with open(os.path.join(run_dir, ARITH_REPORT), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot_arithmetic(run_dir, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = {float(k.split("_")[1]): k for k in summary if k.startswith("arith_")}
    keys[0.0] = "baseline"
    coefs = sorted(keys)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(coefs, [summary[keys[c]]["held_out"]["score"] for c in coefs], "s-", label="held-out short texts: left score")
    axes[0].plot(coefs, [summary[keys[c]]["title_only"] for c in coefs], "^-", label="real bills, title only: left alignment")
    axes[0].plot(coefs, [summary[keys[c]]["left_alignment"] for c in coefs], "o-", label="real bills: left alignment")
    axes[0].set(xlabel="coef of (dW_left - dW_right); > 0 = left", ylabel="-1 = right ... +1 = left",
                title="%s: political alignment" % MODEL_ID)
    axes[1].plot(coefs, [summary[keys[c]]["mean_position"] for c in coefs], "o-", label="real bills")
    axes[1].plot(coefs, [(summary[keys[c]]["held_out"]["pos_left"] + summary[keys[c]]["held_out"]["pos_right"]) / 2 for c in coefs],
                 "s-", label="held-out short texts")
    axes[1].set(xlabel="coef", ylabel="-1 = against everything ... +1 = for everything", title="Tendency to approve")
    for ax in axes:
        ax.axhline(0, color="gray", lw=0.5)
        ax.legend()
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(run_dir, ARITH_PLOT), dpi=120)


def variant_name(key):
    """'edit_+0.10' -> 'edit_left_0.10' (coef > 0 points left)."""
    if key == "baseline":
        return key
    kind, coef = key.rsplit("_", 1)
    try:
        return "%s_%s_%.2f" % (kind, "left" if float(coef) > 0 else "right", abs(float(coef)))
    except ValueError:
        return key


def write_run_folder(run_dir, shown, datapoints, prompts, settings, note):
    """Viewer-compatible run folder: config, prompts and one answer per (state, bill); states are variants."""
    messages = {dp["id"]: vp.build_messages(dp, VARIANT, prompts) for dp in datapoints}
    hashes = {i: vp.prompt_hash(m) for i, m in messages.items()}
    with open(os.path.join(run_dir, vp.PROMPTS_LOG), "w", encoding="utf-8") as f:
        for i, m in messages.items():
            f.write(json.dumps({"hash": hashes[i], "variant": VARIANT, "id": i, "messages": m}, ensure_ascii=False) + "\n")
    with open(os.path.join(run_dir, vp.RAW_FILE), "w", encoding="utf-8") as f:
        for key, result in shown.items():
            for i, r in result.items():
                label = max(r["probs"], key=r["probs"].get)
                text = "%s (p_pour=%.2f, p_contre=%.2f, p_abstention=%.2f, probability mass on the three votes=%.2f)" % (
                    VOTE_WORDS[label], r["probs"]["for"], r["probs"]["against"], r["probs"]["abstain"], r["mass"])
                f.write(json.dumps({"model": MODEL_NAME, "variant": variant_name(key), "id": i, "sample": 0,
                                    "prompt_hash": hashes[i], "settings": dict(settings, state=key), "text": text,
                                    "label": label, "usage": {"cost": 0}, "error": None,
                                    "time": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False) + "\n")
    config = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "models": [MODEL_NAME], "variants": [variant_name(k) for k in shown],
              "n_samples": 1, "settings": {MODEL_NAME: dict(settings, max_text_chars=MAX_TEXT_CHARS)},
              "datapoints": [dp["id"] for dp in datapoints], "prompts": prompts, "note": note}
    with open(os.path.join(run_dir, vp.CONFIG_FILE), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=1)


def write_outputs(run_dir, evals, datapoints, prompts, tok, layer, reader, prefill, strongest):
    """Run folder, report and plot of the rank-1 edit experiment."""
    coef_of = lambda k: float(k.rsplit("_", 1)[1])
    edits = sorted((k for k in evals if k.startswith("edit_")), key=coef_of)  # from most right to most left
    shown = [k for k in edits if coef_of(k) < 0] + ["baseline"] + [k for k in edits if coef_of(k) > 0]
    write_run_folder(run_dir, {k: evals[k] for k in shown}, datapoints, prompts, {"layer": layer, "prefill": prefill},
                     "WEIGHT STEERING of %s: rank-1 edit of layer %d's MLP, left/right, %d divisive bills" % (
                         MODEL_ID, layer, len(datapoints)))
    summary = {k: alignment(e, datapoints) for k, e in evals.items()}
    with open(os.path.join(run_dir, "weights_summary.json"), "w", encoding="utf-8") as f:
        json.dump({"layer": layer, "reader": reader, "summary": summary}, f, indent=1)
    write_report(run_dir, summary, layer, reader, len(datapoints))
    plot(run_dir, summary, layer)
    vp.write_report(run_dir)


def write_report(run_dir, summary, layer, reader, n_bills):
    base = summary["baseline"]
    f2 = lambda x: "-" if x is None else "%+.2f" % x
    lines = ["# Weight steering of %s" % MODEL_ID, "",
             "%d divisive bills of at most %d characters, %d with left and right opposed (%d supported by the left, "
             "%d opposed by it). Steered layer: %d. Baseline left alignment: %s." % (
                 n_bills, MAX_TEXT_CHARS, base["n_opposed"], base["n_left_bills"], base["n_right_bills"], layer,
                 f2(base["left_alignment"])), "",
             "- **coef**: norm of the added direction, as a fraction of the typical residual norm; positive = towards the left.",
             "- **hook**: the direction is added to the layer's output at inference (activation steering).",
             "- **edit**: the same direction written into the weights (rank-1 change of the MLP output matrix).",
             "- **random**: same edit with a random direction of the same norm (control).",
             "- **left alignment**: (mean position on bills the left supports - on bills it opposes) / 2; "
             "+1 = votes like the left, -1 = like the right.",
             "- **mass**: probability that the first answer token is one of the three votes (near 1 = the model still answers properly).",
             "", "Reader quality: on %d held-out tokens, u . activation = %.2f +/- %.2f (target 1), so the edit adds "
             "the direction on every token, as the hook does." % (reader["n_heldout"], reader["mean"], reader["std"]), "",
             "| coef | hook: left alignment | edit: left alignment | edit: mean position | edit: mass | edit: votes | random: left alignment |",
             "|---|---|---|---|---|---|---|"]
    coefs = sorted({float(k.rsplit("_", 1)[1]) for k in summary if k != "baseline"})
    for coef in coefs[:len(coefs) // 2] + [0.0] + coefs[len(coefs) // 2:]:
        if coef == 0.0:
            lines.append("| 0 (baseline) | %s | %s | %s | %.2f | %s | %s |" % (f2(base["left_alignment"]), f2(base["left_alignment"]),
                         f2(base["mean_position"]), base["mass"], base["labels"], f2(base["left_alignment"])))
            continue
        h, e, r = (summary["%s_%+.2f" % (k, coef)] for k in ("hook", "edit", "random"))
        lines.append("| %+.2f | %s | **%s** | %s | %.2f | %s | %s |" % (coef, f2(h["left_alignment"]), f2(e["left_alignment"]),
                     f2(e["mean_position"]), e["mass"], e["labels"], f2(r["left_alignment"])))
    with open(os.path.join(run_dir, REPORT_FILE), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(run_dir, summary, layer):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    coefs = sorted({float(k.rsplit("_", 1)[1]) for k in summary if k != "baseline"} | {0.0})
    get = lambda kind, c, field: summary["baseline"][field] if c == 0 else summary["%s_%+.2f" % (kind, c)][field]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for kind, style in (("hook", "o--"), ("edit", "s-"), ("random", "x:")):
        axes[0].plot(coefs, [get(kind, c, "left_alignment") for c in coefs], style, label=kind)
        axes[1].plot(coefs, [get(kind, c, "mass") for c in coefs], style, label=kind)
    axes[0].axhline(summary["baseline"]["left_alignment"], color="gray", lw=0.5)
    axes[0].set(xlabel="coef (fraction of the residual norm; > 0 = left)", ylabel="left alignment",
                title="%s, layer %d: steering the votes" % (MODEL_ID, layer))
    axes[1].set(xlabel="coef", ylabel="probability mass on the three votes", title="Does the model still answer properly?")
    for ax in axes:
        ax.legend()
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(run_dir, PLOT_FILE), dpi=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["probe", "sweep", "run", "arithmetic", "extract"])
    parser.add_argument("--layer", type=int, help="run: layer to steer (default: best of the last sweep)")
    parser.add_argument("--prefill", default="**", help="text forced at the start of the model's answer")
    parser.add_argument("--direction", choices=["persona", "statements"], default="persona")
    parser.add_argument("--train", choices=sorted(ADAPTER_SCHEDULE), default="proposals", help="arithmetic: texts the adapters learn from")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.step == "extract":
        extract_titles()
        return
    torch.manual_seed(SEED)
    prompts = vp.load_prompts()
    datapoints = bills()
    tok, model = load_model()
    token_ids = vote_token_ids(tok)
    logger.info("%s loaded: %d layers, hidden %d; %d bills; vote tokens %s", MODEL_ID, len(model.model.layers),
                model.config.hidden_size, len(datapoints), {k: [tok.decode([i]) for i in ids] for k, ids in token_ids.items()})
    ctx = (tok, model, datapoints, prompts, token_ids, args.prefill)
    if args.step == "probe":
        probe(tok, model, datapoints, prompts)
        t0 = time.time()
        base = evaluate(*ctx)
        print("baseline (%.0f s):" % (time.time() - t0), alignment(base, datapoints))
    elif args.step == "sweep":
        sweep(ctx, args.direction)
    elif args.step == "arithmetic":
        arithmetic(ctx, args.train)
    else:
        layer = args.layer
        if layer is None:
            with open(SWEEP_FILE, encoding="utf-8") as f:
                layer = json.load(f)["best_layer"]
        run(ctx, layer, args.direction)


if __name__ == "__main__":
    main()
