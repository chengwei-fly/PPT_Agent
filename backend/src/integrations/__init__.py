"""Local integration package.

Bridges external generation engine and agent framework:

- `AgentScope/`  — installed in editable mode via
  `backend/scripts/install_local_deps.sh` (or .bat). It is a real
  Python package, importable as `import agentscope`.

- SVG-to-PPTX generation engine — provides the scripts for
  converting SVG slides to native PPTX format. Bridged at runtime
  by `svg_pptx_bridge.py` which injects the scripts directory
  onto `sys.path`.

Public surface:
    from src.integrations.agentscope_compat import Agent, ReActAgent, HarnessAgent
    from src.integrations.svg_pptx_bridge import create_pptx_with_native_svg
"""
