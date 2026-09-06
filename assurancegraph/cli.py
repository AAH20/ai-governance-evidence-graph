from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .change import impact
from .core import assess, load_case
from .economics import calculate
from .exporters import dumps, intoto_statement, markdown_brief, offline_html, oscal_assessment


def _write(path: str, content: str) -> None: Path(path).write_text(content)


def main() -> None:
    parser=argparse.ArgumentParser(prog="assurancegraph",description="Continuous AI governance evidence graph and assurance case compiler")
    sub=parser.add_subparsers(dest="command",required=True)
    validate=sub.add_parser("validate"); validate.add_argument("case")
    compile_cmd=sub.add_parser("compile"); compile_cmd.add_argument("case"); compile_cmd.add_argument("--as-of"); compile_cmd.add_argument("--output",required=True); compile_cmd.add_argument("--fail-on",choices=["never","restricted","reject"],default="reject")
    change=sub.add_parser("change-impact"); change.add_argument("case"); change.add_argument("change"); change.add_argument("--output",required=True)
    export=sub.add_parser("export"); export.add_argument("case"); export.add_argument("--format",choices=["oscal","intoto","markdown","html"],required=True); export.add_argument("--as-of"); export.add_argument("--output",required=True)
    econ=sub.add_parser("economics"); econ.add_argument("inputs"); econ.add_argument("--output",required=True)
    args=parser.parse_args()
    if args.command=="economics": _write(args.output,dumps(calculate(json.loads(Path(args.inputs).read_text())))); return
    case=load_case(args.case)
    if args.command=="validate": print(dumps({"case_id":case["case_id"],"valid":True}),end=""); return
    if args.command=="change-impact": _write(args.output,dumps(impact(case,json.loads(Path(args.change).read_text())))); return
    as_of=date.fromisoformat(args.as_of) if args.as_of else None
    assessment=assess(case,as_of)
    if args.command=="compile":
        _write(args.output,dumps(assessment))
        if args.fail_on=="reject" and assessment["decision"]=="REJECT": raise SystemExit(2)
        if args.fail_on=="restricted" and assessment["decision"]!="APPROVE": raise SystemExit(2)
        return
    if args.format=="oscal": content=dumps(oscal_assessment(case,assessment))
    elif args.format=="intoto": content=dumps(intoto_statement(case,assessment))
    else:
        md=markdown_brief(case,assessment); content=md if args.format=="markdown" else offline_html(md)
    _write(args.output,content)


if __name__=="__main__": main()
