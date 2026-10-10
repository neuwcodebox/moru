"""Turn Danbooru records into concise prompt-writing lookup results."""

from moru.danbooru.http import TagLookupError


def tag_name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("invalid tag name")
    name = "_".join(value.strip().lower().split())
    metatags = {
        "rating",
        "order",
        "status",
        "user",
        "id",
        "score",
        "filetype",
        "source",
        "is",
        "has",
    }
    if (
        any(char in name for char in '*",\\\n\r')
        or name.startswith(("-", "~"))
        or (":" in name and name.split(":", 1)[0] in metatags)
    ):
        raise ValueError("expected one tag or concept, not a post search")
    return name


def _records(value):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TagLookupError()
    return value


def _usable_names(records, limit, *, exclude=None):
    names = []
    for item in _records(records):
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise TagLookupError()
        if not isinstance(item.get("is_deprecated"), bool):
            raise TagLookupError()
        count = item.get("post_count")
        if type(count) is not int or count < 0:
            raise TagLookupError()
        if not item["is_deprecated"] and count > 0 and name != exclude and name not in names:
            names.append(name)
    return names[:limit]


def _description(wiki):
    if wiki is None:
        return None
    if not isinstance(wiki, dict) or not isinstance(wiki.get("body"), str):
        raise TagLookupError()
    body = wiki["body"].strip()
    if len(body) > 3000:
        body = body[:2988].rstrip() + " [truncated]"
    return body or None


class DanbooruTags:
    def __init__(self, http):
        self.http = http

    def search_tags(self, query, limit, cancelled):
        query = tag_name(query)
        results = self.http.get(
            "/autocomplete.json",
            {
                "search[type]": "tag_query",
                "search[query]": query,
                "limit": limit,
            },
            cancelled,
        )
        tags = []
        for item in _records(results):
            record = item.get("tag")
            if not isinstance(record, dict) or item.get("value") != record.get("name"):
                raise TagLookupError()
            tags.append(record)
        return _usable_names(tags, limit)

    def get_tag_info(self, name, cancelled):
        name = tag_name(name)
        aliases = _records(
            self.http.get(
                "/tag_aliases.json",
                {
                    "search[antecedent_name]": name,
                    "search[status]": "active",
                    "limit": 1,
                    "only": "antecedent_name,consequent_name,status",
                },
                cancelled,
            )
        )
        if aliases:
            alias = aliases[0]
            if alias.get("status") != "active" or alias.get("antecedent_name") != name:
                raise TagLookupError()
            canonical = alias.get("consequent_name")
            if not isinstance(canonical, str) or not canonical:
                raise TagLookupError()
            name = canonical
        records = _records(
            self.http.get(
                "/tags.json",
                {
                    "search[name]": name,
                    "limit": 1,
                    "only": "name,is_deprecated,wiki_page[body]",
                },
                cancelled,
            )
        )
        if records:
            record = records[0]
            if record.get("name") != name or type(record.get("is_deprecated")) is not bool:
                raise TagLookupError()
            result = {"name": name, "description": _description(record.get("wiki_page"))}
            if record["is_deprecated"]:
                result["deprecated"] = True
            return result
        wikis = _records(
            self.http.get(
                "/wiki_pages.json",
                {
                    "search[title]": name,
                    "search[is_deleted]": "false",
                    "limit": 1,
                    "only": "title,body",
                },
                cancelled,
            )
        )
        if wikis and wikis[0].get("title") != name:
            raise TagLookupError()
        return {"name": None, "description": _description(wikis[0] if wikis else None)}

    def get_related_tags(self, name, limit, cancelled):
        name = tag_name(name)
        result = self.http.get(
            "/related_tag.json",
            {
                "query": name,
                "category": "general",
                "order": "cosine",
                "limit": limit + 1,
            },
            cancelled,
        )
        if not isinstance(result, dict) or not isinstance(result.get("related_tags"), list):
            raise TagLookupError()
        source = result.get("tag")
        canonical = source.get("name") if isinstance(source, dict) else name
        tags = []
        for item in _records(result["related_tags"]):
            if not isinstance(item.get("tag"), dict):
                raise TagLookupError()
            tags.append(item["tag"])
        return {
            "cooccurring": _usable_names(tags, limit, exclude=canonical),
            "wiki_links": _usable_names(result.get("wiki_page_tags"), limit, exclude=canonical),
        }
