"""Local integration package.

Bridges the external agent framework and the internal rendering library:

- `AgentScope/`  — installed in editable mode via
  `backend/scripts/install_local_deps.sh` (or .bat). It is a real
  Python package, importable as `import agentscope`.

- Internal PPTX rendering library — packages the SVG → PPTX
  conversion pipeline at `src.integrations.ppt_engine`. Bridged at
  runtime by `pptx_render_bridge.py`, which injects the scripts
  directory onto `sys.path` and re-exports a stable surface.

Public surface:
    from src.integrations.agentscope_compat import Agent, ReActAgent, HarnessAgent
    from src.integrations.pptx_render_bridge import create_pptx_with_native_svg
"""
