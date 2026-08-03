from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_api import AgentApiServer
from epiphan_sdk import EpiphanKVM_SDK


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AgentKVM2USB local JSON API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runtime-root")
    parser.add_argument("--profile-root")
    args = parser.parse_args()

    sdk = EpiphanKVM_SDK(runtime_root=args.runtime_root, profile_root=args.profile_root)
    server = AgentApiServer(sdk, host=args.host, port=args.port)
    print(f"AgentKVM2USB API listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        sdk.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
