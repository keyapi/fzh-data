from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np

from .candidates import CandidateProduct


@dataclass(frozen=True)
class PairExample:
    query_id: str
    msku: str
    asin: str
    product: CandidateProduct
    label: int
    features: dict[str, float]


class RankingModel:
    def __init__(self, seed: int = 42, booster: lgb.Booster | None = None):
        self.seed = seed
        self.booster = booster
        self.feature_names: tuple[str, ...] = (
            tuple(booster.feature_name()) if booster is not None else ()
        )

    def fit(self, examples: list[PairExample]) -> "RankingModel":
        ordered = sorted(examples, key=lambda example: example.query_id)
        query_rows: dict[str, list[PairExample]] = {}
        for example in ordered:
            query_rows.setdefault(example.query_id, []).append(example)
        invalid = [
            query_id
            for query_id, rows in query_rows.items()
            if not any(row.label > 0 for row in rows) or not any(row.label == 0 for row in rows)
        ]
        if invalid:
            raise ValueError(f"Ranking queries need positive and negative candidates: {invalid[:5]}")

        self.feature_names = tuple(sorted({name for row in ordered for name in row.features}))
        matrix = np.asarray(
            [[row.features.get(name, 0.0) for name in self.feature_names] for row in ordered],
            dtype=float,
        )
        labels = np.asarray([row.label for row in ordered], dtype=int)
        groups = [len(rows) for rows in query_rows.values()]
        dataset = lgb.Dataset(
            matrix,
            label=labels,
            group=groups,
            feature_name=list(self.feature_names),
            free_raw_data=False,
        )
        self.booster = lgb.train(
            {
                "objective": "lambdarank",
                "metric": "ndcg",
                "ndcg_eval_at": [1, 3, 5, 20],
                "learning_rate": 0.05,
                "num_leaves": 15,
                "min_data_in_leaf": 1,
                "feature_pre_filter": False,
                "verbosity": -1,
                "seed": self.seed,
                "feature_fraction_seed": self.seed,
                "bagging_seed": self.seed,
                "deterministic": True,
                "force_col_wise": True,
                "num_threads": 1,
            },
            dataset,
            num_boost_round=60,
        )
        return self

    def predict(self, examples: list[PairExample]) -> list[float]:
        if self.booster is None:
            raise RuntimeError("Ranking model is not fitted")
        matrix = np.asarray(
            [[row.features.get(name, 0.0) for name in self.feature_names] for row in examples],
            dtype=float,
        )
        return [float(value) for value in self.booster.predict(matrix)]

    def save(self, path: Path) -> None:
        if self.booster is None:
            raise RuntimeError("Ranking model is not fitted")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.booster.model_to_string(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RankingModel":
        return cls(booster=lgb.Booster(model_str=path.read_text(encoding="utf-8")))


class _DisjointSet:
    def __init__(self, values):
        self.parent = {value: value for value in values}

    def find(self, value):
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left, right):
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def grouped_split(
    examples: list[PairExample], validation_fraction: float = 0.2, seed: int = 42
) -> tuple[list[PairExample], list[PairExample]]:
    query_ids = sorted({example.query_id for example in examples})
    if len(query_ids) < 2:
        return list(examples), []

    groups = _DisjointSet(query_ids)
    by_msku: dict[str, str] = {}
    by_asin: dict[str, str] = {}
    for example in examples:
        if example.msku:
            previous = by_msku.setdefault(example.msku.lower(), example.query_id)
            groups.union(previous, example.query_id)
        if example.asin:
            previous = by_asin.setdefault(example.asin.upper(), example.query_id)
            groups.union(previous, example.query_id)

    clusters: dict[str, set[str]] = {}
    for query_id in query_ids:
        clusters.setdefault(groups.find(query_id), set()).add(query_id)
    cluster_values = list(clusters.values())
    random.Random(seed).shuffle(cluster_values)

    validation_target = max(1, round(len(query_ids) * validation_fraction))
    validation_ids: set[str] = set()
    for cluster in cluster_values:
        if validation_ids and len(validation_ids) >= validation_target:
            break
        if len(validation_ids) + len(cluster) < len(query_ids):
            validation_ids.update(cluster)
    if not validation_ids:
        validation_ids.update(cluster_values[0])

    train = [example for example in examples if example.query_id not in validation_ids]
    validation = [example for example in examples if example.query_id in validation_ids]
    return train, validation


def evaluate_rankings(
    rankings: dict[str, list[tuple[str, float, int]]], at: tuple[int, ...] = (1, 3, 5, 20)
) -> dict[str, float]:
    query_count = len(rankings)
    metrics: dict[str, float] = {"queries": float(query_count)}
    if not query_count:
        metrics.update({f"recall_at_{position}": 0.0 for position in at})
        metrics["mrr"] = 0.0
        return metrics

    reciprocal_rank = 0.0
    hits = {position: 0 for position in at}
    for rows in rankings.values():
        ordered = sorted(rows, key=lambda row: row[1], reverse=True)
        positive_ranks = [index for index, row in enumerate(ordered, start=1) if row[2] > 0]
        if positive_ranks:
            rank = positive_ranks[0]
            reciprocal_rank += 1 / rank
            for position in at:
                hits[position] += int(rank <= position)
    for position in at:
        metrics[f"recall_at_{position}"] = hits[position] / query_count
    metrics["mrr"] = reciprocal_rank / query_count
    return metrics
