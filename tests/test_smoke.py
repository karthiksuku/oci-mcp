import importlib

def test_imports():
    mod = importlib.import_module("oci_mcp_server")
    assert hasattr(mod, "mcp"), "FastMCP instance not found"
