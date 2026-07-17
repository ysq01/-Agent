from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import make_engine, make_session_factory
from app.services.evaluation import (
    DEFAULT_EVAL_CASES_PATH,
    DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH,
    DEFAULT_EVAL_MARKDOWN_PATH,
    DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH,
    DEFAULT_EVAL_REPORT_PATH,
    load_eval_cases,
    run_evaluation,
    write_evaluation_reports,
)
from app.services.policy_knowledge import ingest_knowledge_base


def main() -> None:
    parser = argparse.ArgumentParser(description="Run customer service Agent evaluation.")
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_EVAL_CASES_PATH),
        help="Path to JSONL or JSON eval cases.",
    )
    parser.add_argument(
        "--json-report",
        default=None,
        help=(
            "Path to write JSON report. Defaults to eval_report.json for rules "
            "and eval_report_llm_assisted.json for llm_assisted."
        ),
    )
    parser.add_argument(
        "--markdown-report",
        default=None,
        help=(
            "Path to write Markdown report. Defaults to eval_report.md for rules "
            "and eval_report_llm_assisted.md for llm_assisted."
        ),
    )
    parser.add_argument(
        "--skip-knowledge-ingest",
        action="store_true",
        help="Skip idempotent knowledge ingestion before evaluation.",
    )
    parser.add_argument(
        "--persist-db-changes",
        action="store_true",
        help=(
            "Persist ticket writes from invoice/complaint cases. Default is rollback "
            "after report generation."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["rules", "llm_assisted"],
        default="rules",
        help="Agent processing mode for evaluation. Default keeps the deterministic rules baseline.",
    )
    args = parser.parse_args()
    json_report_path, markdown_report_path = resolve_report_paths(
        mode=args.mode,
        json_report=args.json_report,
        markdown_report=args.markdown_report,
    )

    if not args.skip_knowledge_ingest:
        ingestion = ingest_knowledge_base()
        print(
            "Knowledge ready: "
            f"collection={ingestion.collection_name}, "
            f"documents={ingestion.document_count}, chunks={ingestion.chunk_count}."
        )

    cases = load_eval_cases(Path(args.cases))
    engine = make_engine()

    try:
        if args.persist_db_changes:
            session_factory = make_session_factory(engine)
            with session_factory() as session:
                report = run_evaluation(session, cases, mode=args.mode)
        else:
            with engine.connect() as connection:
                transaction = connection.begin()
                session = Session(
                    bind=connection,
                    autoflush=False,
                    expire_on_commit=False,
                )
                try:
                    report = run_evaluation(session, cases, mode=args.mode)
                finally:
                    session.close()
                    transaction.rollback()

        write_evaluation_reports(
            report,
            json_path=json_report_path,
            markdown_path=markdown_report_path,
            write_history=True,
        )
    finally:
        engine.dispose()

    print(
        "Evaluation completed: "
        f"mode={args.mode}, "
        f"total={report.total_cases}, passed={report.passed_cases}, "
        f"failed={report.failed_cases}, "
        f"intent_accuracy={report.metrics.intent_accuracy:.2%}, "
        f"tool_call_accuracy={report.metrics.tool_call_accuracy:.2%}, "
        f"policy_hit_rate={report.metrics.policy_hit_rate:.2%}, "
        f"average_latency_ms={report.metrics.average_latency_ms:.2f}."
    )
    print(f"JSON report: {json_report_path}")
    print(f"Markdown report: {markdown_report_path}")
    if not args.persist_db_changes:
        print("Database writes from eval cases were rolled back.")


def resolve_report_paths(
    *,
    mode: str,
    json_report: str | None,
    markdown_report: str | None,
) -> tuple[Path, Path]:
    if mode == "llm_assisted":
        default_json = DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH
        default_markdown = DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH
    else:
        default_json = DEFAULT_EVAL_REPORT_PATH
        default_markdown = DEFAULT_EVAL_MARKDOWN_PATH

    return (
        Path(json_report) if json_report else default_json,
        Path(markdown_report) if markdown_report else default_markdown,
    )


if __name__ == "__main__":
    main()
