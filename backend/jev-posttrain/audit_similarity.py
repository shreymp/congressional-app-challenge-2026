"""Measure exact and high lexical overlap between prepared train/holdout calls."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "prepared"


def read(name: str) -> list[dict]:
    return [json.loads(s) for s in (DATA / f"{name}.jsonl").read_text().splitlines()]


def transcript(r: dict) -> str:
    return r["text"].split("Context:\n", 1)[1].rsplit("\n\nEvaluate proposition:", 1)[0]


def main() -> None:
    train, validation, test = read("train"), read("validation"), read("test")
    assert not ({r["text_sha256"] for r in train} & {r["text_sha256"] for r in validation + test})
    all_rows = train + validation + test
    vec = TfidfVectorizer(analyzer="char", ngram_range=(4, 5), min_df=2, max_features=70000)
    matrix = vec.fit_transform([transcript(r) for r in all_rows])
    train_vectors = matrix[:len(train)]
    result = {"method": "maximum character 4-5 gram TF-IDF cosine similarity to any train dialogue", "exact_overlap": 0, "splits": {}}
    for split, start, rows in (("validation", len(train), validation), ("test", len(train) + len(validation), test)):
        maxima = []
        for offset in range(start, start + len(rows), 100):
            maxima.extend((matrix[offset:min(offset + 100, start + len(rows))] @ train_vectors.T).max(axis=1).toarray().ravel().tolist())
        scores = np.asarray(maxima)
        by_source = {}
        for source in sorted({r["source"] for r in rows}):
            source_scores = scores[np.array([r["source"] == source for r in rows])]
            by_source[source] = {"n": len(source_scores), "at_least_0_8": int((source_scores >= .8).sum()), "at_least_0_9": int((source_scores >= .9).sum())}
        result["splits"][split] = {"n": len(rows), "median": float(np.median(scores)), "p90": float(np.quantile(scores, .9)), "at_least_0_8": int((scores >= .8).sum()), "at_least_0_9": int((scores >= .9).sum()), "by_source": by_source}
    path = HERE / "runs" / "similarity_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
