"""Extract a parameterized MiniMax H3 API prompt from a ComfyUI UI workflow.

Reads the original workflow; never changes it or submits generation. Only the
selected SaveVideo and its dependencies are retained. Nested subgraphs resolve
through their input/output bindings. Python standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import urllib.request

if __package__:
    from .paths import relative_path
else:
    from paths import relative_path


MISSING = object()
H3_CONDITIONING = {"MiniMaxH3ReferenceToVideo", "MiniMaxH3ImageToVideo"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def widget_values(node):
    named = node.get("widgets_values_named")
    if named is not None:
        return {key: value for key, value in named.items() if key != "control_after_generate"}
    names = [i["name"] for i in node.get("inputs", []) if "widget" in i]
    values = node.get("widgets_values", [])
    if len(values) != len(names):
        # Seed's frontend-only control_after_generate is not an API argument.
        if node["type"] == "RandomNoise" and len(values) == len(names) + 1:
            values = values[:1]
        elif values:
            raise ValueError(f"Cannot safely map widgets for {node['type']} #{node['id']}")
    return dict(zip(names, values))


def normalize_link(link):
    if isinstance(link, list):
        keys = ("id", "origin_id", "origin_slot", "target_id", "target_slot", "type")
        return dict(zip(keys, link))
    return link


class GraphContext:
    def __init__(self, builder, graph, prefix="", parent=None, instance=None):
        self.builder, self.graph, self.prefix = builder, graph, prefix
        self.parent, self.instance = parent, instance
        self.nodes = {str(n["id"]): n for n in graph["nodes"]}
        self.links = {str(l["id"]): l for l in map(normalize_link, graph["links"])}
        self.children = {}

    def input_value(self, node, name):
        entry = next((i for i in node.get("inputs", []) if i["name"] == name), {})
        if entry.get("link") is not None:
            link = self.links[str(entry["link"])]
            return self.output_value(str(link["origin_id"]), link["origin_slot"])
        return widget_values(node).get(name, MISSING)

    def output_value(self, node_id, slot):
        if self.parent and node_id == str(self.graph["inputNode"]["id"]):
            name = self.graph["inputs"][slot]["name"]
            return self.parent.input_value(self.instance, name)
        node = self.nodes[node_id]
        definition = self.builder.definitions.get(node["type"])
        if definition:
            if node_id not in self.children:
                self.children[node_id] = GraphContext(
                    self.builder, definition, self.prefix + node_id + "_", self, node
                )
            child = self.children[node_id]
            output_id = str(definition["outputNode"]["id"])
            links = [l for l in child.links.values()
                     if str(l["target_id"]) == output_id and l["target_slot"] == slot]
            if len(links) != 1:
                raise ValueError(f"Subgraph {node_id} output {slot} has {len(links)} bindings")
            link = links[0]
            return child.output_value(str(link["origin_id"]), link["origin_slot"])
        if node["type"] == "PathchSageAttentionKJ" and self.builder.args.no_sage:
            return self.input_value(node, "model")
        if node["type"] == "MiniMaxH3TurboLoRA" and self.builder.args.no_turbo:
            return self.input_value(node, "model")
        self.builder.emit(self, node)
        return [self.prefix + node_id, slot]


class PromptBuilder:
    def __init__(self, workflow, args):
        self.args = args
        self.definitions = {g["id"]: g for g in workflow.get("definitions", {}).get("subgraphs", [])}
        self.prompt = {}
        self.visiting = set()
        self.root = GraphContext(self, workflow)
        self.frames = max(5, round(args.seconds * 24))
        self.frames += (5 - self.frames % 17) % 17
        if self.frames / 24 > 10:
            raise ValueError("Frame alignment exceeds 10 seconds; use 9.4 seconds or less")

    def emit(self, context, node):
        node_id = context.prefix + str(node["id"])
        if node_id in self.prompt:
            return
        if node_id in self.visiting:
            raise ValueError(f"Cycle at node {node_id}")
        if node.get("mode", 0) != 0:
            raise ValueError(f"Reachable node {node_id} is muted/bypassed; choose a valid output")
        self.visiting.add(node_id)
        kind = node["type"]
        overrides = {}
        omitted = set()
        if kind == "MiniMaxH3TurboSampler" and self.args.no_turbo:
            kind = "KSamplerSelect"
            overrides["sampler_name"] = "res_multistep"
        elif kind in H3_CONDITIONING:
            overrides.update(prompt=self.args.text, width=self.args.width,
                             height=self.args.height, length=self.frames)
            omitted.update(i["name"] for i in node.get("inputs", [])
                           if i["name"].startswith("ref_") or i["name"] in ("first_frame", "last_frame"))
            if kind == "MiniMaxH3ReferenceToVideo":
                overrides["ref_image_size"] = "match"
                for index in range(len(self.args.image)):
                    overrides[f"ref_images.ref_image_{index}"] = [f"input_image_{index}", 0]
            else:
                if len(self.args.image) > 2:
                    raise ValueError("ImageToVideo accepts only first and optional last image")
                overrides["first_frame"] = ["input_image_0", 0]
                if len(self.args.image) == 2:
                    overrides["last_frame"] = ["input_image_1", 0]
        elif kind == "RandomNoise":
            overrides["noise_seed"] = self.args.seed
        elif kind == "BasicScheduler":
            if self.args.steps is not None:
                overrides["steps"] = self.args.steps
        elif kind == "SaveVideo":
            overrides.update(filename_prefix=self.args.output_prefix, format="mp4", codec="auto")
        elif kind == "CreateVideo":
            overrides["fps"] = 24
        elif kind == "CLIPLoader" and self.args.clip_device:
            overrides["device"] = self.args.clip_device
        names = set(widget_values(node)) | {i["name"] for i in node.get("inputs", [])}
        inputs = {}
        for name in sorted(names - omitted - overrides.keys()):
            value = context.input_value(node, name)
            if value is not MISSING:
                inputs[name] = value
        inputs.update(overrides)
        self.prompt[node_id] = {"class_type": kind, "inputs": inputs}
        self.visiting.remove(node_id)

    def build(self):
        outputs = sorted((n for n in self.root.nodes.values()
                          if n["type"] == "SaveVideo" and n.get("mode", 0) == 0),
                         key=lambda n: int(n["id"]))
        if self.args.output_node:
            outputs = [n for n in outputs if str(n["id"]) == self.args.output_node]
        if not outputs:
            raise ValueError("No matching active top-level SaveVideo output")
        self.output_id = str(outputs[0]["id"])
        self.emit(self.root, outputs[0])
        if not any(n["class_type"] in H3_CONDITIONING for n in self.prompt.values()):
            raise ValueError("Selected output does not depend on MiniMax H3 conditioning")
        for index, filename in enumerate(self.args.image):
            self.prompt[f"input_image_{index}"] = {"class_type": "LoadImage", "inputs": {"image": filename}}
        if any(n["class_type"] == "RTXVideoSuperResolution" for n in self.prompt.values()):
            raise ValueError("Selected output uses RTX upscaling; select the original-resolution output")
        turbo = any(n["class_type"] == "MiniMaxH3TurboSampler" for n in self.prompt.values())
        if turbo and self.args.steps is None:
            for n in self.prompt.values():
                if n["class_type"] == "BasicScheduler":
                    n["inputs"]["steps"] = 4
        if self.args.steps is not None and self.args.steps < 4:
            raise ValueError("This tool requires at least 4 sampling steps")
        return self.prompt


def validate_schema(prompt, info):
    """Check available classes, required fields, links, scalar ranges and model names.

    This is read-only structural validation, not ComfyUI execution validation.
    LoadImage file existence is checked by ComfyUI when a request is submitted.
    """
    errors = []
    for node_id, node in prompt.items():
        kind, values = node["class_type"], node["inputs"]
        if kind not in info:
            errors.append(f"{node_id}: unavailable class {kind}")
            continue
        schema = info[kind].get("input", {})
        all_fields = {**schema.get("required", {}), **schema.get("optional", {})}
        for name in schema.get("required", {}):
            if name not in values:
                errors.append(f"{node_id}: missing required {name}")
        for name, value in values.items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                source = prompt.get(value[0])
                if source is None:
                    errors.append(f"{node_id}.{name}: unknown source {value[0]}")
                elif source["class_type"] in info and not 0 <= value[1] < len(info[source["class_type"]]["output"]):
                    errors.append(f"{node_id}.{name}: invalid source output {value[1]}")
                continue
            entry = all_fields.get(name)
            if entry is None:
                parent = name.split(".", 1)[0]
                if parent not in all_fields or all_fields[parent][0] != "COMFY_AUTOGROW_V3":
                    errors.append(f"{node_id}: unknown input {name}")
                continue
            field_type = entry[0]
            options = entry[1] if len(entry) > 1 else {}
            choices = field_type if isinstance(field_type, list) else options.get("options")
            if choices and all(isinstance(c, str) for c in choices) and value not in choices:
                errors.append(f"{node_id}.{name}: value unavailable: {value}")
            if field_type in ("INT", "FLOAT") and isinstance(value, (int, float)):
                if value < options.get("min", -math.inf) or value > options.get("max", math.inf):
                    errors.append(f"{node_id}.{name}: outside schema range")
    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", required=True, type=Path)
    parser.add_argument("--image", required=True, action="append", help="Uploaded ComfyUI input filename; repeat for refs")
    text = parser.add_mutually_exclusive_group(required=True)
    text.add_argument("--prompt")
    text.add_argument("--prompt-file", type=Path)
    parser.add_argument("--seed", type=int, default=2026091201)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--width", type=int, default=896)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, help="Defaults to 4 with Turbo; preserves source otherwise")
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--output-node", help="Top-level SaveVideo ID; defaults to the lowest ID")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--no-sage", action="store_true", help="Omit the optional KJ SageAttention model patch")
    parser.add_argument("--no-turbo", action="store_true",
                        help="Remove Turbo LoRA and replace its sampler with res_multistep; requires --steps 20")
    parser.add_argument("--clip-device", choices=["cpu", "default"])
    schema = parser.add_mutually_exclusive_group()
    schema.add_argument("--object-info", type=Path, help="Validate against a saved /object_info response")
    schema.add_argument("--server", help="Read /object_info for validation, e.g. http://127.0.0.1:8188")
    args = parser.parse_args()
    if not 0 < args.seconds <= 10 or not math.isfinite(args.seconds):
        parser.error("--seconds must be greater than 0 and at most 10")
    if any(v < 32 or v % 32 for v in (args.width, args.height)):
        parser.error("Width and height must be positive multiples of 32")
    if not 0 <= args.seed < 2**64:
        parser.error("Seed must be an unsigned 64-bit integer")
    if args.no_turbo and args.steps != 20:
        parser.error("--no-turbo requires explicitly passing --steps 20")
    if not 1 <= len(args.image) <= 9:
        parser.error("Provide between 1 and 9 reference images")
    for value in [*args.image, args.output_prefix]:
        portable = value.replace("\\", "/")
        if ":" in portable or portable.startswith("/") or ".." in PurePosixPath(portable).parts:
            parser.error("Images and output prefix must be relative ComfyUI paths without '..'")
    if args.workflow.resolve() in (args.output.resolve(), args.output.with_suffix(".meta.json").resolve()):
        parser.error("Output must differ from the original workflow")
    for destination in (args.output, args.output.with_suffix(".meta.json")):
        if destination.exists():
            parser.error(f"Output already exists: {destination}; use a new filename for this attempt")
    args.text = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8-sig")
    if not args.text.strip():
        parser.error("Prompt must not be empty")
    try:
        builder = PromptBuilder(read_json(args.workflow), args)
        prompt = builder.build()
        info = None
        if args.object_info:
            info = read_json(args.object_info)
        elif args.server:
            with urllib.request.urlopen(args.server.rstrip("/") + "/object_info", timeout=30) as response:
                info = json.load(response)
        if info is not None:
            validate_schema(prompt, info)
        metadata = {
            "path_base": ".", "source_workflow": relative_path(args.workflow, args.output.parent),
            "source_sha256": hashlib.sha256(args.workflow.read_bytes()).hexdigest(),
            "output_node": builder.output_id, "node_count": len(prompt),
            "width": args.width, "height": args.height, "fps": 24,
            "requested_seconds": args.seconds, "frames": builder.frames,
            "generated_seconds": builder.frames / 24, "seed": args.seed,
            "steps": [n["inputs"]["steps"] for n in prompt.values() if n["class_type"] == "BasicScheduler"],
            "turbo_removed": args.no_turbo,
            "schema_checked": info is not None,
            "generation_submitted": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(prompt, ensure_ascii=False, indent=2) + "\n")
        with args.output.with_suffix(".meta.json").open("x", encoding="utf-8") as output:
            output.write(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"output": str(args.output), **metadata}, ensure_ascii=True, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
