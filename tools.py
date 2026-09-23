"""Tool router: tell the assistant which tool groups a prompt needs or can skip."""


def questions(cfg, ctx):
    return {f"tool:{g}": {"type": "noul",
                          "instructions": f"Will handling the request in `prompt` need {desc}?"}
            for g, desc in cfg["groups"].items()}


def route(cfg, answers, session, ctx):
    use, skip = [], []
    for g in cfg["groups"]:
        if f"tool:{g}" not in answers:
            continue
        p = answers[f"tool:{g}"]["noul"]
        if p >= cfg["use_threshold"]:
            use.append(g)
        elif p <= cfg["skip_threshold"]:
            skip.append(g)
    parts = []
    if use:
        parts.append("Tools likely needed: " + ", ".join(use) + ".")
    if skip:
        parts.append("Tools not needed, skip them: " + ", ".join(skip) + ".")
    return " ".join(parts), {"use": use, "skip": skip}
