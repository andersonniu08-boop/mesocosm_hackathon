import argparse
from bench_common.env_sdk import serve
from env import PongSummarizationEnv

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"PongSummarizationEnv adapter -> http://{args.host}:{args.port}")
    serve(PongSummarizationEnv, host=args.host, port=args.port)
