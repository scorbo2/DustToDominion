#!/usr/bin/env python3
"""Command line client for the sd-server native API (/sdcpp/v1).

Submits an image generation job to a running sd-server, polls the job to
completion, and writes each result image to disk. Standard library only.

Generation options left unset are omitted from the request entirely, so
server startup defaults and recipe defaults keep applying.
"""

import argparse
import base64
import json
import mimetypes
import os
import socket
import sys
import time
import urllib.error
import urllib.request

DEFAULT_SERVER = "http://127.0.0.1:1234"
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_REQUEST_TIMEOUT = 30.0
FINAL_JOB_STATES = ("completed", "failed", "cancelled")
CACHE_MODES = ("disabled", "easycache", "ucache", "dbcache", "taylorseer",
               "cache-dit", "spectrum")
IMAGE_FIELDS = ("init_image", "mask_image", "ref_images", "control_image")
FORMAT_EXTENSIONS = {"png": "png", "jpeg": "jpg", "webp": "webp"}
STATUS_HINTS = {
    503: "no model is loaded (or it is still loading); start sd-server with "
         "model arguments or POST /sdcpp/v1/models/load",
    429: "the server job queue is full; try again later",
    410: "the job no longer exists on the server",
}


class ServerError(Exception):
    """A server-side or transport failure with a user-presentable message."""


class ServerClient:
    """JSON-over-HTTP access bound to one sd-server base URL."""

    def __init__(self, base_url, timeout):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_json(self, path):
        return self._request_json(path)

    def post_json(self, path, payload):
        return self._request_json(path, payload)

    def _request_json(self, path, payload=None):
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data,
                                         headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ServerError(self._describe_http_error(exc, path)) from None
        except urllib.error.URLError as exc:
            raise ServerError(
                f"cannot reach sd-server at {self.base_url}: {exc.reason}. "
                "Is the server running, and is --server correct?"
            ) from None
        except (TimeoutError, socket.timeout):
            raise ServerError(
                f"sd-server at {self.base_url} did not respond within "
                f"{self.timeout}s"
            ) from None

    def _describe_http_error(self, exc, path):
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (ValueError, OSError):
            body = {}
        parts = [f"HTTP {exc.code} from {self.base_url}{path}"]
        server_message = body.get("error") or body.get("code")
        if server_message:
            parts.append(f"server said: {server_message}")
        hint = STATUS_HINTS.get(exc.code)
        if hint:
            parts.append(f"hint: {hint}")
        return "; ".join(parts)


def positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if number < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value}")
    return number


def unit_float(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}")
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError(f"expected a value in 0..1, got {value}")
    return number


def percent_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if not 0 <= number <= 100:
        raise argparse.ArgumentTypeError(f"expected a value in 0..100, got {value}")
    return number


def encode_image_file(path):
    """Read a local image and return it as a data URL for the API."""
    try:
        with open(path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
    except OSError as exc:
        raise SystemExit(f"error: cannot read image {path!r}: {exc.strerror}")
    mime_type = mimetypes.guess_type(path)[0] or "image/png"
    return f"data:{mime_type};base64,{encoded}"


def parse_lora_spec(spec):
    """Parse "path" or "path:multiplier"; a non-numeric suffix stays part of
    the path so Windows drive letters and odd filenames survive."""
    head, separator, tail = spec.rpartition(":")
    if separator:
        try:
            return {"path": head, "multiplier": float(tail)}
        except ValueError:
            pass
    return {"path": spec}


def copy_when_set(payload, entries):
    for key, value in entries:
        if value is not None:
            payload[key] = value


def build_sample_params(args):
    params = {}
    copy_when_set(params, (
        ("sample_method", args.sample_method),
        ("scheduler", args.scheduler),
        ("sample_steps", args.steps),
        ("eta", args.eta),
        ("shifted_timestep", args.shifted_timestep),
        ("flow_shift", args.flow_shift),
    ))
    guidance = {}
    copy_when_set(guidance, (
        ("txt_cfg", args.cfg_scale),
        ("img_cfg", args.img_cfg_scale),
        ("distilled_guidance", args.distilled_guidance),
    ))
    if guidance:
        params["guidance"] = guidance
    return params


def build_hires(args):
    hires = {"enabled": True}
    copy_when_set(hires, (
        ("upscaler", args.hires_upscaler),
        ("scale", args.hires_scale),
        ("steps", args.hires_steps),
        ("denoising_strength", args.hires_denoising_strength),
    ))
    return hires


def parse_dimensions(value):
    width, separator, height = value.lower().partition("x")
    try:
        parsed = (int(width), int(height))
    except ValueError:
        parsed = None
    if not separator or parsed is None or min(parsed) < 1:
        raise SystemExit(f"error: --tile-size expects WIDTHxHEIGHT, got {value!r}")
    return parsed


def build_payload(args):
    payload = {"prompt": args.prompt}
    copy_when_set(payload, (
        ("negative_prompt", args.negative_prompt),
        ("width", args.width),
        ("height", args.height),
        ("seed", args.seed),
        ("batch_count", args.batch_count),
        ("clip_skip", args.clip_skip),
        ("strength", args.strength),
        ("control_strength", args.control_strength),
        ("embed_image_metadata", args.embed_metadata),
        ("preview", args.preview),
        ("preview_interval", args.preview_interval),
        ("output_format", args.output_format),
        ("output_compression", args.output_compression),
    ))

    copy_when_set(payload, (
        ("init_image", encode_image_file(args.init_image) if args.init_image else None),
        ("mask_image", encode_image_file(args.mask) if args.mask else None),
        ("control_image", encode_image_file(args.control_image) if args.control_image else None),
    ))
    if args.ref_image:
        payload["ref_images"] = [encode_image_file(p) for p in args.ref_image]

    copy_when_set(payload, (
        ("cache_mode", args.cache_mode or None),
        ("cache_option", args.cache_option),
    ))

    sample_params = build_sample_params(args)
    if sample_params:
        payload["sample_params"] = sample_params
    if args.lora:
        payload["lora"] = [parse_lora_spec(spec) for spec in args.lora]
    if args.hires:
        payload["hires"] = build_hires(args)
    if args.vae_tiling:
        tiling = {"enabled": True}
        if args.tile_size:
            tiling["tile_size_w"], tiling["tile_size_h"] = parse_dimensions(args.tile_size)
        payload["vae_tiling_params"] = tiling
    return payload


def redact_for_display(payload):
    redacted = dict(payload)
    for field in IMAGE_FIELDS:
        if field in redacted:
            redacted[field] = "<image data omitted>"
    return redacted


def submit_generation(client, payload):
    return client.post_json("/sdcpp/v1/img_gen", payload)


def show_progress(job):
    preview = job.get("preview")
    if preview:
        text = (f"{job['status']}: pass {preview['pass']}, step "
                f"{preview['step']}/{preview['total_steps']}")
    elif job["status"] == "queued":
        text = f"queued (position {job.get('queue_position', '?')})"
    else:
        text = job["status"]
    sys.stderr.write(f"\r{text:<78}")
    sys.stderr.flush()


def cancel_job(client, poll_path):
    print("\ninterrupted: asking the server to cancel the job...",
          file=sys.stderr)
    try:
        client.post_json(f"{poll_path}/cancel", {})
        job = client.get_json(poll_path)
        if job["status"] not in FINAL_JOB_STATES:
            print(f"note: job is still '{job['status']}'; it may finish "
                  "despite the cancel request", file=sys.stderr)
        return job
    except ServerError as exc:
        print(f"warning: cancellation request failed: {exc}", file=sys.stderr)
        return None


def await_job(client, poll_path, poll_interval):
    try:
        while True:
            job = client.get_json(poll_path)
            show_progress(job)
            if job["status"] in FINAL_JOB_STATES:
                sys.stderr.write("\n")
                return job
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        return cancel_job(client, poll_path)


def numbered_path(base_path, index, count):
    if count == 1 or index <= 0:
        return base_path
    root, ext = os.path.splitext(base_path)
    return f"{root}_{index}{ext}"


def save_images(result, output_path):
    images = result.get("images") or []
    if not images:
        raise ServerError("job completed but the server returned no images")
    if output_path is None:
        ext = FORMAT_EXTENSIONS.get(result.get("output_format", "png"), "png")
        output_path = f"output.{ext}"
    saved = []
    for position, image in enumerate(images):
        path = numbered_path(output_path, image.get("index", position), len(images))
        try:
            with open(path, "wb") as handle:
                handle.write(base64.b64decode(image["b64_json"]))
        except OSError as exc:
            raise ServerError(f"cannot write {path!r}: {exc.strerror}") from None
        saved.append(path)
    return saved


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="sd-client.py",
        description="Generate an image via the sd-server native API "
                    "(/sdcpp/v1). Unset options are omitted from the request "
                    "so server and recipe defaults apply.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s "a cat sitting on a chair" --width 1024 --height 1024
  %(prog)s "sunset over mountains" --cfg-scale 7 --steps 28 --seed 42
  %(prog)s "restore this photo" --init-image input.png --strength 0.55
  %(prog)s "portrait" --lora style.safetensors:0.8 --hires --hires-scale 1.5
  %(prog)s "dragon" --server http://gpu-box:1234 -o dragon.png

notes:
  --lora paths resolve on the SERVER, relative to its LoRA directories;
  query GET /sdcpp/v1/capabilities for sampler, scheduler, upscaler and
  LoRA names. Ctrl-C during polling asks the server to cancel the job.
  Exit codes: 0 success, 1 usage or server error, 2 argparse usage error,
  130 interrupted.
""",
    )

    connection = parser.add_argument_group("connection")
    connection.add_argument("--server", default=DEFAULT_SERVER,
                            help=f"sd-server base URL (default: {DEFAULT_SERVER})")
    connection.add_argument("--request-timeout", type=positive_int,
                            default=int(DEFAULT_REQUEST_TIMEOUT), metavar="SECONDS",
                            help="per-request HTTP timeout (default: 30)")
    connection.add_argument("--poll-interval", type=float,
                            default=DEFAULT_POLL_INTERVAL, metavar="SECONDS",
                            help="job poll interval (default: 2.0)")

    generation = parser.add_argument_group("generation")
    generation.add_argument("prompt", help="text prompt")
    generation.add_argument("--negative-prompt", help="negative prompt")
    generation.add_argument("--width", type=positive_int, metavar="PIXELS")
    generation.add_argument("--height", type=positive_int, metavar="PIXELS")
    generation.add_argument("--steps", type=positive_int,
                            help="sampling steps (sample_params.sample_steps)")
    generation.add_argument("--cfg-scale", type=float, metavar="SCALE",
                            help="text CFG (sample_params.guidance.txt_cfg)")
    generation.add_argument("--img-cfg-scale", type=float, metavar="SCALE",
                            help="image CFG (sample_params.guidance.img_cfg)")
    generation.add_argument("--distilled-guidance", type=float, metavar="SCALE",
                            help="distilled guidance embedding strength")
    generation.add_argument("--sample-method", metavar="NAME",
                            help="sampler, e.g. euler, euler_a, dpmpp_2_m_sde")
    generation.add_argument("--scheduler", metavar="NAME",
                            help="scheduler, e.g. discrete, simple, karras")
    generation.add_argument("--eta", type=float, metavar="VALUE",
                            help="sampler eta, where the sampler uses it")
    generation.add_argument("--shifted-timestep", type=int, metavar="VALUE",
                            help="SDXL timestep shifting")
    generation.add_argument("--flow-shift", type=float, metavar="VALUE",
                            help="flow shift, where the scheduler uses it")
    generation.add_argument("--clip-skip", type=int, metavar="VALUE")
    generation.add_argument("--seed", type=int, metavar="VALUE",
                            help="-1 requests a random seed")
    generation.add_argument("--batch-count", type=positive_int, metavar="N",
                            help="images per job")
    generation.add_argument("--cache-mode", choices=CACHE_MODES,
                            help="feature cache mode")
    generation.add_argument("--cache-option", metavar="STRING",
                            help="algorithm-specific cache option string")
    generation.add_argument("--preview", choices=("none", "proj", "tae", "vae"),
                            help="live preview mode; frames drive progress output")
    generation.add_argument("--preview-interval", type=positive_int, metavar="N",
                            help="emit a preview every N sample steps (default: 1)")

    inputs = parser.add_argument_group("image inputs (local files, uploaded base64)")
    inputs.add_argument("--init-image", metavar="PATH",
                        help="image-to-image init image")
    inputs.add_argument("--strength", type=unit_float, metavar="VALUE",
                        help="image-to-image denoising strength, 0..1")
    inputs.add_argument("--mask", metavar="PATH",
                        help="inpainting mask; requires --init-image")
    inputs.add_argument("--control-image", metavar="PATH",
                        help="ControlNet control image")
    inputs.add_argument("--control-strength", type=float, metavar="VALUE",
                        help="ControlNet strength")
    inputs.add_argument("--ref-image", action="append", metavar="PATH",
                        help="reference image; repeatable")

    loras = parser.add_argument_group("loras (resolved on the server)")
    loras.add_argument("--lora", action="append", metavar="PATH[:MULT]",
                       help="server-side LoRA path with optional multiplier; "
                            "repeatable")

    post = parser.add_argument_group("post-processing")
    post.add_argument("--hires", action="store_true",
                      help="enable the highres second pass")
    post.add_argument("--hires-upscaler", metavar="NAME",
                      help="upscaler name from GET /sdcpp/v1/capabilities")
    post.add_argument("--hires-scale", type=float, metavar="FACTOR",
                      help="highres scale factor")
    post.add_argument("--hires-steps", type=positive_int, metavar="N",
                      help="highres second-pass steps")
    post.add_argument("--hires-denoising-strength", type=unit_float, metavar="VALUE",
                      help="highres second-pass denoising strength, 0..1")
    post.add_argument("--vae-tiling", action="store_true",
                      help="enable VAE tiling")
    post.add_argument("--tile-size", metavar="WxH",
                      help="VAE tile size in image pixels, e.g. 512x512")

    output = parser.add_argument_group("output")
    output.add_argument("-o", "--output", metavar="PATH",
                        help="output file; extra batch images get _N suffixes "
                             "(default: output.png / output_N.ext)")
    output.add_argument("--output-format", choices=("png", "jpeg", "webp"),
                        help="encoded output format (default: png)")
    output.add_argument("--output-compression", type=percent_int, metavar="PCT",
                        help="output quality, 0..100 (default: 100)")
    output.add_argument("--embed-metadata", action=argparse.BooleanOptionalAction,
                        default=None,
                        help="embed generation parameters in image metadata "
                             "(--no-embed-metadata to disable)")
    output.add_argument("--print-request", action="store_true",
                        help="print the request JSON (image data redacted) "
                             "before submitting")

    args = parser.parse_args(argv)
    if args.mask and not args.init_image:
        parser.error("--mask requires --init-image")
    if args.tile_size and not args.vae_tiling:
        parser.error("--tile-size requires --vae-tiling")
    hires_options = (args.hires_upscaler, args.hires_scale, args.hires_steps,
                     args.hires_denoising_strength)
    if not args.hires and any(v is not None for v in hires_options):
        parser.error("highres options require --hires")
    return args


def run(argv):
    args = parse_args(argv)
    client = ServerClient(args.server, args.request_timeout)
    payload = build_payload(args)
    if args.print_request:
        print(json.dumps(redact_for_display(payload), indent=2))

    submission = submit_generation(client, payload)
    print(f"job {submission['id']} accepted ({submission['status']})")

    job = await_job(client, submission["poll_url"], args.poll_interval)
    if job is None:
        return 130
    if job["status"] != "completed":
        error = job.get("error") or {}
        print(f"job ended as '{job['status']}': "
              f"{error.get('message', 'no message')} "
              f"(code: {error.get('code', 'unknown')})", file=sys.stderr)
        return 1

    for path in save_images(job["result"], args.output):
        print(f"saved {path}")
    return 0


def main(argv=None):
    try:
        return run(argv)
    except ServerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(file=sys.stderr)
        sys.exit(130)
