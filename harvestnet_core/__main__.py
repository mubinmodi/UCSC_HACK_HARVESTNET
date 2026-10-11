import argparse
import json
from pathlib import Path
from .evaluation import evaluate,replay
from .engine import run_fixture

parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['run','evaluate','replay'])
parser.add_argument('path')
parser.add_argument('--output',default='runtime/replays')
args=parser.parse_args()
if args.command=='replay': result=replay(args.path)
else:
    fixture=json.loads(Path(args.path).read_text(encoding='utf-8'))
    result=evaluate(fixture,output=args.output) if args.command=='evaluate' else run_fixture(fixture)
print(json.dumps(result,indent=2,allow_nan=False))
