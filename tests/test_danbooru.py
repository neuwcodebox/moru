from threading import Event

import pytest
from support.danbooru import Catalog, tag

from moru.chatgpt.tools import DanbooruTools
from moru.danbooru.http import TagLookupError
from moru.danbooru.tags import DanbooruTags
from moru.errors import MoruError


def test_search_returns_only_distinct_usable_canonical_names_with_a_bounded_limit():
    catalog = Catalog(
        [
            {"value": "grey_hair", "antecedent": "gray_hair", "tag": tag("grey_hair")},
            {"value": "grey_hair", "tag": tag("grey_hair")},
            {"value": "old_tag", "tag": tag("old_tag", is_deprecated=True)},
            {"value": "empty_tag", "tag": tag("empty_tag", post_count=0)},
            {"value": "white_hair", "tag": tag("white_hair")},
        ]
    )
    assert DanbooruTags(catalog).search_tags("gray hair", 1, Event()) == ["grey_hair"]
    assert catalog.calls[0][1] == {
        "search[type]": "tag_query",
        "search[query]": "gray_hair",
        "limit": 1,
    }


def test_tag_info_resolves_an_active_alias_and_returns_only_its_name_and_description():
    catalog = Catalog(
        [{"antecedent_name": "gray_hair", "consequent_name": "grey_hair", "status": "active"}],
        [tag("grey_hair", wiki_page={"body": "Hair that is colored grey."})],
    )
    assert DanbooruTags(catalog).get_tag_info("gray hair", Event()) == {
        "name": "grey_hair",
        "description": "Hair that is colored grey.",
    }
    assert catalog.calls[1][1]["search[name]"] == "grey_hair"


def test_missing_tag_can_still_provide_a_wiki_without_inventing_a_canonical_tag():
    catalog = Catalog([], [], [{"title": "silver_hair", "body": "Use grey hair or white hair."}])
    assert DanbooruTags(catalog).get_tag_info("silver_hair", Event()) == {
        "name": None,
        "description": "Use grey hair or white hair.",
    }


def test_missing_tag_and_missing_wiki_are_a_successful_empty_lookup():
    assert DanbooruTags(Catalog([], [], [])).get_tag_info("missing", Event()) == {
        "name": None,
        "description": None,
    }


def test_tag_info_marks_deprecated_tags_without_recommending_an_invented_replacement():
    catalog = Catalog([], [tag("old_tag", is_deprecated=True, wiki_page=None)])
    assert DanbooruTags(catalog).get_tag_info("old_tag", Event()) == {
        "name": "old_tag",
        "description": None,
        "deprecated": True,
    }


def test_long_wiki_text_is_bounded_and_marked_as_truncated():
    catalog = Catalog([], [tag("grey_hair", wiki_page={"body": "a" * 5000})])
    result = DanbooruTags(catalog).get_tag_info("grey_hair", Event())
    assert len(result["description"]) <= 3000
    assert result["description"].endswith("[truncated]")


def test_related_results_separate_cooccurrence_from_wiki_references_and_remove_self():
    catalog = Catalog(
        {
            "tag": tag("grey_hair"),
            "related_tags": [
                {"tag": tag("grey_hair"), "frequency": 1},
                {"tag": tag("long_hair"), "frequency": 0.7},
                {"tag": tag("old_tag", is_deprecated=True)},
            ],
            "wiki_page_tags": [tag("white_hair"), tag("grey_hair")],
        }
    )
    assert DanbooruTags(catalog).get_related_tags("grey_hair", 20, Event()) == {
        "cooccurring": ["long_hair"],
        "wiki_links": ["white_hair"],
    }
    assert catalog.calls[0][1]["order"] == "cosine"
    assert catalog.calls[0][1]["category"] == "general"


@pytest.mark.parametrize("reply", [{}, [{"value": "grey_hair"}], "not json records"])
def test_malformed_catalog_responses_are_lookup_errors(reply):
    with pytest.raises(TagLookupError):
        DanbooruTags(Catalog(reply)).search_tags("grey_hair", 20, Event())


@pytest.mark.parametrize(
    "name,args",
    [
        ("search_tags", {"query": "rating:g", "limit": 20}),
        ("search_tags", {"query": "hair", "limit": True}),
        ("search_tags", {"query": "hair", "limit": 0}),
        ("search_tags", {"query": "hair", "limit": 21}),
        ("get_tag_info", {"name": ""}),
        ("get_tag_info", {"name": "grey_hair", "url": "https://example.com"}),
        ("delete_tag", {"name": "grey_hair"}),
    ],
)
def test_invalid_tool_arguments_do_not_query_the_catalog(name, args):
    catalog = Catalog()
    result = DanbooruTools(DanbooruTags(catalog)).execute(name, args, Event())
    assert "error" in result
    assert catalog.calls == []


@pytest.mark.parametrize(
    "name,args",
    [
        ("search_tags", {"query": "hair"}),
        ("get_tag_info", {"name": "grey_hair"}),
        ("get_related_tags", {"name": "grey_hair"}),
    ],
)
def test_failed_lookup_is_an_explicit_tool_result_and_does_not_raise(name, args):
    tools = DanbooruTools(DanbooruTags(Catalog(TagLookupError())))
    assert tools.execute(name, args, Event()) == {
        "error": "lookup_unavailable",
    }


def test_cancelled_lookup_propagates_cancellation_instead_of_becoming_an_optional_failure():
    tools = DanbooruTools(DanbooruTags(Catalog(MoruError("GENERATION_CANCELLED"))))
    with pytest.raises(MoruError) as error:
        tools.execute("search_tags", {"query": "hair"}, Event())
    assert error.value.code == "GENERATION_CANCELLED"


def test_tool_contract_exposes_three_independent_functions_with_small_outputs():
    tools = DanbooruTools(DanbooruTags(Catalog([])))
    namespace = tools.definitions()[0]
    assert namespace["type"] == "namespace" and namespace["name"] == "danbooru"
    assert {tool["name"] for tool in namespace["tools"]} == {
        "search_tags",
        "get_tag_info",
        "get_related_tags",
    }
    assert tools.execute("search_tags", {"query": "missing", "limit": None}, Event()) == []


@pytest.mark.parametrize("name", ["fate/stay_night", "re:zero_kara_hajimeru_isekai_seikatsu"])
def test_copyright_tag_punctuation_is_preserved_in_lookup_arguments(name):
    catalog = Catalog([])
    assert (
        DanbooruTools(DanbooruTags(catalog)).execute(
            "search_tags",
            {"query": name},
            Event(),
        )
        == []
    )
    assert catalog.calls[0][1]["search[query]"] == name
