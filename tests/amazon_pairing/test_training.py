from amazon_pairing.attributes import AttributeValue, ListingAttributes
from amazon_pairing.candidates import CandidateProduct
from amazon_pairing.training import CandidateRetriever, FamilyClassifier, TrainingListing, build_pair_examples


EMPTY = ListingAttributes(AttributeValue(), AttributeValue(), AttributeValue(), AttributeValue())


def test_family_classifier_returns_ranked_families():
    rows = [
        TrainingListing("triangle-grey-153", "triangle wedge pillow grey", "A1", "KS0001-A", "KS0001"),
        TrainingListing("triangle-blue-194", "triangle wedge pillow blue", "A2", "KS0001-B", "KS0001"),
        TrainingListing("strip-grey-100", "long bolster strip pillow", "B1", "KS0002-A", "KS0002"),
        TrainingListing("strip-blue-200", "long bolster strip cushion", "B2", "KS0002-B", "KS0002"),
    ]

    classifier = FamilyClassifier(seed=3).fit(rows)
    families = classifier.predict("triangle-taupe-153", "triangle wedge pillow taupe", top_k=2)

    assert families[0][0] == "KS0001"
    assert len(families) == 2


def test_pair_example_builder_keeps_positive_and_hard_negatives():
    listings = [
        TrainingListing("triangle-grey-153", "grey triangle pillow 153 cm", "A1", "KS0001-A", "KS0001")
    ]
    catalog = [
        CandidateProduct("KS0001-A", "KS0001", "grey triangle pillow 153", EMPTY),
        CandidateProduct("KS0001-B", "KS0001", "blue triangle pillow 153", EMPTY),
        CandidateProduct("KS0001-C", "KS0001", "grey triangle pillow 194", EMPTY),
    ]

    examples, recall = build_pair_examples(listings, catalog, max_candidates=3)

    assert recall == 1.0
    assert sum(example.label for example in examples) == 1
    assert {example.product.sku for example in examples} == {"KS0001-A", "KS0001-B", "KS0001-C"}


def test_candidate_retriever_reports_miss_without_injecting_positive():
    listing = TrainingListing("alpha-alpha", "alpha alpha", "A1", "KS0001-C", "KS0001")
    catalog = [
        CandidateProduct("KS0001-A", "KS0001", "alpha alpha", EMPTY),
        CandidateProduct("KS0001-B", "KS0001", "beta beta", EMPTY),
        CandidateProduct("KS0001-C", "KS0001", "gamma gamma", EMPTY),
    ]
    retriever = CandidateRetriever(catalog)

    examples, recall = build_pair_examples(
        [listing], catalog, max_candidates=1, retriever=retriever, inject_positive=False
    )

    assert recall == 0.0
    assert all(example.label == 0 for example in examples)


def test_batch_retrieval_matches_single_query_retrieval():
    catalog = [
        CandidateProduct("KS0001-A", "KS0001", "alpha triangle", EMPTY),
        CandidateProduct("KS0001-B", "KS0001", "beta triangle", EMPTY),
    ]
    retriever = CandidateRetriever(catalog)
    queries = [("alpha", "triangle", ("KS0001",)), ("beta", "triangle", ("KS0001",))]

    batch = retriever.retrieve_many(queries, limit=1)

    assert batch == [retriever.retrieve(*query, limit=1) for query in queries]


def test_retriever_keeps_all_reliable_attribute_matches_before_lexical_cutoff():
    grey_153 = ListingAttributes(
        AttributeValue(("153",), True), AttributeValue(("灰色",), True),
        AttributeValue(), AttributeValue()
    )
    catalog = [
        CandidateProduct("KS0001-A", "KS0001", "unrelated", grey_153),
        CandidateProduct("KS0001-B", "KS0001", "alpha alpha", EMPTY),
        CandidateProduct("KS0001-C", "KS0001", "alpha alpha", EMPTY),
    ]
    retriever = CandidateRetriever(catalog)

    selected = retriever.retrieve("alpha", "alpha", ("KS0001",), limit=1, attributes=grey_153)

    assert selected == [0]


def test_training_builder_adds_conflicting_hard_negative_when_only_positive_survives():
    grey = ListingAttributes(
        AttributeValue(("153",), True), AttributeValue(("灰色",), True),
        AttributeValue(), AttributeValue()
    )
    blue = ListingAttributes(
        AttributeValue(("153",), True), AttributeValue(("蓝色",), True),
        AttributeValue(), AttributeValue()
    )
    listing = TrainingListing("grey-153", "grey pillow 153 cm", "A1", "KS0001-A", "KS0001")
    catalog = [
        CandidateProduct("KS0001-A", "KS0001", "grey pillow", grey),
        CandidateProduct("KS0001-B", "KS0001", "blue pillow", blue),
    ]

    examples, _ = build_pair_examples([listing], catalog, max_candidates=2, inject_positive=True)

    assert {example.label for example in examples} == {0, 1}
    negative = next(example for example in examples if example.label == 0)
    assert negative.features["color_contradiction"] == 1.0


def test_build_pair_examples_accepts_predictions_aligned_per_listing():
    catalog = [
        CandidateProduct("KS0001-A", "KS0001", "first", EMPTY),
        CandidateProduct("KS0002-A", "KS0002", "second", EMPTY),
    ]
    listings = [
        TrainingListing("SAME-MSKU", "first", "ASIN-1", "KS0001-A", "KS0001"),
        TrainingListing("SAME-MSKU", "second", "ASIN-2", "KS0002-A", "KS0002"),
    ]

    examples, recall = build_pair_examples(
        listings,
        catalog,
        max_candidates=1,
        predicted_families=[("KS0001",), ("KS0002",)],
        inject_positive=False,
    )

    assert recall == 1.0
    assert [example.product.family for example in examples] == ["KS0001", "KS0002"]
