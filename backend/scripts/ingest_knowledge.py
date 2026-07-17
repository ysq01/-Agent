from app.services.policy_knowledge import DEFAULT_KNOWLEDGE_DIR, ingest_knowledge_base


def main() -> None:
    result = ingest_knowledge_base()
    print(
        "Knowledge ingestion completed: "
        f"collection={result.collection_name}, "
        f"documents={result.document_count}, "
        f"chunks={result.chunk_count}, "
        f"points={result.point_count}, "
        f"source={DEFAULT_KNOWLEDGE_DIR}"
    )


if __name__ == "__main__":
    main()
