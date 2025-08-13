#!/usr/bin/env python3
import os, asyncio
from oci_mcp_server import oci_manager

async def main():
    print("🧪 Testing OCI connectivity...")
    try:
        identity = oci_manager.get_client("identity")
        tenancy = identity.get_tenancy(oci_manager.config['tenancy']).data
        print("✅ Tenancy:", tenancy.name)
        print("   Home region key:", tenancy.home_region_key)
        print("   Region:", oci_manager.config.get("region"))
    except Exception as e:
        print("❌ Failed:", e)
        raise

if __name__ == "__main__":
    asyncio.run(main())
