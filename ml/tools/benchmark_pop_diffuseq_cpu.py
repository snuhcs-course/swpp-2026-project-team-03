"""Benchmark the released Pop-DiffuSeq checkpoint on CPU.

This runs the same 10-step DPM-Solver++ sampling computation used by the
repository's decode script. Inputs have the checkpoint's fixed shape of 512
tokens; the benchmark measures model loading, sampling, and token projection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=110)
    return parser.parse_args()


def main() -> None:
    cli = parse_args()
    repo = cli.repo.resolve()
    checkpoint = cli.checkpoint.resolve()
    os.environ.setdefault("HF_HOME", str(checkpoint.parent / ".hf-cache"))
    os.chdir(repo)
    sys.path.insert(0, str(repo))

    from basic_utils import args_to_dict, create_model_and_diffusion, load_defaults_config
    from dpm_solver_pytorch import DPM_Solver, NoiseScheduleVP, model_wrapper

    started = time.perf_counter()
    with (checkpoint.parent / "training_args.json").open(encoding="utf-8") as stream:
        settings = json.load(stream)
    settings["config_name"] = str(repo / "diffuseq" / "bert-model-config" / "config.json")
    settings["device"] = torch.device("cpu")
    model_args = SimpleNamespace(**settings)

    model, diffusion = create_model_and_diffusion(
        **args_to_dict(model_args, load_defaults_config().keys())
    )
    state = torch.load(checkpoint, map_location="cpu")
    model.load_state_dict(state)
    model.eval()
    load_seconds = time.perf_counter() - started

    torch.manual_seed(cli.seed)
    input_ids = torch.full(
        (cli.batch_size, settings["seq_len"]),
        3,
        dtype=torch.long,
        device="cpu",
    )
    # Eleven fixed conditioning positions match the released decode pipeline.
    input_ids[:, 0] = 0
    input_ids[:, 1:10] = 24
    input_ids[:, 10] = 1
    input_mask = torch.ones(
        (cli.batch_size, settings["seq_len"], settings["hidden_dim"]),
        dtype=torch.bool,
        device="cpu",
    )
    input_mask[:, :11, :] = False

    with torch.inference_mode():
        x_start = model.get_embeds(input_ids)
        x_noised = torch.where(input_mask, torch.randn_like(x_start), x_start)
        noise_schedule = NoiseScheduleVP(
            schedule="discrete", betas=torch.from_numpy(diffusion.betas)
        )
        model_fn = model_wrapper(
            model,
            noise_schedule,
            model_type="x_start",
            model_kwargs={},
            guidance_type="uncond",
        )
        solver = DPM_Solver(model_fn, noise_schedule, algorithm_type="dpmsolver++")

        sample_started = time.perf_counter()
        sample = solver.sample(
            x_noised,
            steps=cli.steps,
            order=2,
            skip_type="time_uniform",
            method="multistep",
            input_ids_mask=input_mask,
            x_start=x_start,
        )
        sample_seconds = time.perf_counter() - sample_started

        projection_started = time.perf_counter()
        token_ids = torch.topk(model.get_logits(sample), k=1, dim=-1).indices
        projection_seconds = time.perf_counter() - projection_started

    result = {
        "device": "cpu",
        "torch_version": torch.__version__,
        "threads": torch.get_num_threads(),
        "batch_size": cli.batch_size,
        "sequence_length": settings["seq_len"],
        "hidden_dim": settings["hidden_dim"],
        "solver_steps": cli.steps,
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "load_seconds": load_seconds,
        "sample_seconds": sample_seconds,
        "seconds_per_fragment": sample_seconds / cli.batch_size,
        "projection_seconds": projection_seconds,
        "output_shape": list(token_ids.shape),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
