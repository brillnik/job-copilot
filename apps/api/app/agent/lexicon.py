"""Terms the fact checker treats as claimable skills (lower case).

A term outside this list (and outside the job's own must-haves/keywords and the
configured synonyms) is not checked, so the list errs towards common technologies.
"""

TECH_TERMS = frozenset(
    [
        "python", "java", "javascript", "typescript", "golang", "rust", "c++", "c#",
        "kotlin", "swift", "scala", "ruby", "php", "sql", "react", "angular", "vue",
        "next.js", "node.js", "express", "django", "flask", "fastapi", "spring",
        "rails", "laravel", "postgresql", "mysql", "mongodb", "redis",
        "elasticsearch", "cassandra", "dynamodb", "kafka", "rabbitmq", "kubernetes",
        "docker", "terraform", "ansible", "jenkins", "aws", "gcp", "azure", "lambda",
        "ci/cd", "graphql", "grpc", "spark", "hadoop", "airflow", "pandas", "numpy",
        "pytorch", "tensorflow", "snowflake", "dbt", "tableau", "machine learning",
        "deep learning", "nlp", "llm",
    ]
)  # fmt: skip
