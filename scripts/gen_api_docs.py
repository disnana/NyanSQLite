import inspect
import re
import sys
from pathlib import Path

# Add src to path so we can import nyansqlite
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import nyansqlite  # noqa: F401  # imported for side effects / inspection

METHOD_GROUPS = {
    "Constructor": ["__init__"],
    "Core Methods": ["register", "close", "backend", "registered_models"],
    "CRUD Operations": ["insert", "insert_many", "update", "delete"],
    "Query & Search": ["get", "query", "select", "search", "count", "exists"],
    "Maintenance": ["rebuild_fts", "vacuum"],
    "Raw SQL": ["execute_raw"],
}

GROUP_HEADERS = {
    "Constructor": {"en": "Constructor", "ja": "コンストラクタ"},
    "Core Methods": {"en": "Core Methods", "ja": "コアメソッド"},
    "CRUD Operations": {"en": "CRUD Operations", "ja": "CRUD操作"},
    "Query & Search": {"en": "Query & Search", "ja": "クエリ & 検索"},
    "Maintenance": {"en": "Maintenance", "ja": "メンテナンス"},
    "Raw SQL": {"en": "Raw SQL Execution", "ja": "生のSQL実行"},
    "Other Methods": {"en": "Other Methods", "ja": "その他のメソッド"},
}


def extract_lang(text, lang="ja"):
    if not text:
        return ""

    lines = text.split("\n")
    result_lines = []

    # Simple logic: If a line has Japanese characters, it's for 'ja'.
    # If it's pure ASCII/symbols, it could be for both, but we want to avoid 
    # duplicating description text that was written twice (once in JA, once in EN).
    
    # Improved logic:
    # 1. Example blocks (>>>) are for both.
    # 2. Lines with Japanese are ONLY for 'ja'.
    # 3. Lines without Japanese:
    #    - If 'en', keep them.
    #    - If 'ja', keep them ONLY if there are Japanese characters elsewhere in the same logical block,
    #      or if it's a technical/code line.
    
    for line in lines:
        clean = line.strip()
        if not clean:
            result_lines.append("")
            continue

        if clean.startswith(">>>") or clean.startswith("..."):
            result_lines.append(line)
            continue

        has_ja = bool(re.search(r"[ぁ-んァ-ヶー一-龠]", line))

        if lang == "ja":
            # In JA mode, we keep lines with JA characters, or technical lines.
            # We also keep lines that look like "Args:", "Returns:" etc.
            if has_ja or "`" in line or re.match(r"^(Args|Returns|Raises|Example|引数|戻り値|例外|使用例):", clean, re.I):
                result_lines.append(line)
            elif any(c in line for c in "()[]{}->=:"): # Likely a signature or type hint
                 result_lines.append(line)
        else:
            # In EN mode, we ONLY keep lines that DON'T have Japanese.
            if not has_ja:
                result_lines.append(line)

    return "\n".join(result_lines).strip()


def get_type_name(annotation):
    if annotation == inspect._empty:
        return "Any"
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation).replace("typing.", "").replace("'", "")


def process_repl_blocks(lines):
    result = []
    in_code_block = False
    for line in lines:
        clean = line.strip()
        is_repl = clean.startswith(">>>") or clean.startswith("...")
        if is_repl:
            if not in_code_block:
                result.append("```python")
                in_code_block = True
            # Strip prompt but preserve relative indentation
            stripped_line = re.sub(r"^(\s*)(>>>|\.\.\.)\s?", r"\1", line)
            result.append(stripped_line)
        else:
            if in_code_block:
                result.append("```")
                in_code_block = False
            result.append(line)
    if in_code_block:
        result.append("```")
    return result


def format_docstring(doc, lang="ja", sig=None):
    if not doc:
        return ""

    doc = inspect.cleandoc(doc)
    doc = extract_lang(doc, lang)

    # Initialize segments
    description_lines = []
    args_lines = []
    returns_lines = []
    raises_lines = []
    example_lines = []

    current_section = "description"

    # Simple state machine to parse the docstring
    for line in doc.split("\n"):
        clean = line.strip()

        # Detect section changes
        if re.match(r"^(Args|引数):", clean, re.I):
            current_section = "args"
            continue
        elif re.match(r"^(Returns|戻り値):", clean, re.I):
            current_section = "returns"
            continue
        elif re.match(r"^(Raises|例外):", clean, re.I):
            current_section = "raises"
            continue
        elif re.match(r"^(Example|Examples|使用例):", clean, re.I):
            current_section = "example"
            continue

        if current_section == "description":
            description_lines.append(line)
        elif current_section == "args":
            args_lines.append(line)
        elif current_section == "returns":
            returns_lines.append(line)
        elif current_section == "raises":
            raises_lines.append(line)
        elif current_section == "example":
            example_lines.append(line)

    description_lines = process_repl_blocks(description_lines)
    returns_lines = process_repl_blocks(returns_lines)

    # Build final markdown
    final_md = []

    # Description
    if description_lines:
        final_md.append("\n".join(description_lines).strip() + "\n")

    # Args Table
    if args_lines and sig:
        param_dict = dict(sig.parameters)
        th_name = "引数名" if lang == "ja" else "Parameter"
        th_type = "型" if lang == "ja" else "Type"
        th_desc = "説明" if lang == "ja" else "Description"
        final_md.append(f"#### {th_name}\n")
        final_md.append(f"| {th_name} | {th_type} | {th_desc} |")
        final_md.append("|---|---|---|")

        # Parse descriptions into a dict to deduplicate
        parsed_args = {}
        last_arg = None
        for line in args_lines:
            m = re.match(r"^\s*([\w_]+)\s*\(([\w_]+)\):(.*)$", line.strip())
            if m:
                p_name, p_type_hint, p_desc = m.groups()
                parsed_args[p_name] = p_desc.strip()
                last_arg = p_name
                continue

            m = re.match(r"^\s*([\w_]+):(.*)$", line.strip())
            if m:
                p_name, p_desc = m.groups()
                parsed_args[p_name] = p_desc.strip()
                last_arg = p_name
            elif line.strip() and last_arg:
                parsed_args[last_arg] += " " + line.strip()

        # Iterate over signature parameters to retain order and include all args
        for p_name, p_param in param_dict.items():
            if p_name == "self":
                continue

            p_desc = parsed_args.get(p_name, "")
            p_type = get_type_name(p_param.annotation)
            p_type_text = f"`{p_type}`" if p_type != "Any" else ""

            # If no description in docstring, try to find it (for ja/en mixed)
            if not p_desc:
                 # Try to search for the param name in args_lines even if the regex didn't catch it
                 for line in args_lines:
                     if p_name in line and ":" in line:
                         p_desc = line.split(":", 1)[1].strip()
                         break

            # If no description in docstring, we still list the argument if it has a type
            if p_desc or p_type_text:
                final_md.append(f"| `{p_name}` | {p_type_text} | {p_desc} |")

        final_md.append("\n")

    # Returns section
    if returns_lines:
        val_name = "戻り値" if lang == "ja" else "Returns"
        final_md.append(f"#### {val_name}")
        ret_type = "Any"
        if sig and sig.return_annotation != inspect._empty:
            ret_type = get_type_name(sig.return_annotation)

        if ret_type != "Any" and ret_type != "None":
            final_md.append(f"\n**Type:** `{ret_type}`\n")
        else:
            final_md.append("\n")
        final_md.append("\n".join(returns_lines).strip() + "\n")

    # Raises container (VitePress warning)
    if raises_lines:
        title = "例外" if lang == "ja" else "Raises"
        final_md.append(f"::: warning {title}")
        # Make bulleted
        for r_line in raises_lines:
            if r_line.strip() and not r_line.strip().startswith("-"):
                final_md.append(f"- {r_line.strip()}")
            elif r_line.strip():
                final_md.append(r_line.strip())
        final_md.append(":::\n")

    # Example container (VitePress tip)
    if example_lines:
        title = "使用例" if lang == "ja" else "Example"
        final_md.append(f"::: tip {title}")

        example_lines = process_repl_blocks(example_lines)
        has_code_fences = any("```" in line for line in example_lines)
        if not has_code_fences:
            final_md.append("```python")

        for e_line in example_lines:
            final_md.append(e_line)

        if not has_code_fences:
            final_md.append("```")

        final_md.append(":::\n")

    doc = "\n".join(final_md)
    doc = re.sub(r"\n{3,}", "\n\n", doc)

    return doc


def clean_signature(sig_str):
    """Clean the signature string from unnecessary quotes and verbose paths"""
    # Remove quotes around type hints like `: 'str'` -> `: str`
    s = re.sub(r": '([^']+)'", r": \1", sig_str)
    s = re.sub(r"-> '([^']+)'", r"-> \1", s)
    # Remove quotes around complex type hints like `"Literal['a']"` -> `Literal['a']`
    s = re.sub(r': "([^"]+)"', r": \1", s)

    s = s.replace("NoneType", "None")
    # Simplify common generic types
    s = re.sub(r"<CacheType\.[A-Z]+:\s*\'[a-z]+\'>", "CacheType", s)
    return s


def generate_class_md(cls_obj, title, description="", lang="ja"):
    # VitePress frontmatter
    md = "---\n"
    md += "outline: [2, 3]\n"
    md += "---\n\n"
    
    md += f"# {title}\n\n"
    if description:
        md += f"{description}\n\n"

    # Class-level doc
    sig = inspect.signature(cls_obj.__init__)
    # remove `self` from sig if present
    params = list(sig.parameters.values())
    if params and params[0].name == "self":
        sig = sig.replace(parameters=params[1:])

    md += f"## {cls_obj.__name__}\n\n"
    md += f"```python\nclass {cls_obj.__name__}{clean_signature(str(sig))}\n```\n\n"

    # Merge class docstring and __init__ docstring
    full_doc = (cls_obj.__doc__ or "") + "\n\n" + (cls_obj.__init__.__doc__ or "")
    md += format_docstring(full_doc, lang, sig) + "\n\n"
    md += "---\n\n"

    members = inspect.getmembers(cls_obj, predicate=lambda x: inspect.isfunction(x) or inspect.ismethod(x))

    def get_lnum(obj):
        try:
            return inspect.getsourcelines(obj)[1]
        except Exception:
            return 9999

    members.sort(key=lambda x: get_lnum(x[1]))

    # Group methods
    categorized = {k: [] for k in METHOD_GROUPS.keys()}
    categorized["Other Methods"] = []

    for name, method in members:
        if name.startswith("_") and name not in [
            "__init__",
            "__getitem__",
            "__setitem__",
            "__delitem__",
            "__contains__",
            "__len__",
            "__iter__",
        ]:
            continue

        found_group = "Other Methods"
        for group, methods in METHOD_GROUPS.items():
            if name in methods:
                found_group = group
                break

        categorized[found_group].append((name, method))

    # Output groups
    for group, methods_in_group in categorized.items():
        if not methods_in_group:
            continue

        group_title = GROUP_HEADERS[group][lang]
        md += f"## {group_title}\n\n"

        for name, method in methods_in_group:
            if name == "__init__":
                continue  # Skip init as we show it at class level

            sig = inspect.signature(method)
            # Remove self
            params = list(sig.parameters.values())
            if params and params[0].name == "self":
                sig = sig.replace(parameters=params[1:])

            md += f"### `{name}`\n\n"
            md += f"```python\ndef {name}{clean_signature(str(sig))}\n```\n\n"
            doc = format_docstring(method.__doc__, lang, sig)
            if doc:
                md += doc + "\n\n"
            md += "---\n\n"

    return md


def generate_changelog_md():
    root_dir = Path(__file__).parent.parent
    docs_dir = root_dir / "docs" / "site"
    changelog_path = root_dir / "CHANGELOG.md"

    if not changelog_path.exists():
        print(f"Warning: {changelog_path} not found.")
        return

    content = changelog_path.read_text(encoding="utf-8")

    # VitePress frontmatter to show H3 in the right outline
    frontmatter = "---\noutline: [2, 3]\n---\n\n"

    # Simple parsing logic for JA and EN sections
    ja_match = re.search(r"## 日本語\n(.*?)(?=\n## English|$)", content, re.S)
    en_match = re.search(r"## English\n(.*)$", content, re.S)

    if ja_match:
        ja_raw = ja_match.group(1).strip()
        ja_content = frontmatter + "# 更新履歴\n\n" + ja_raw
        (docs_dir / "changelog.md").write_text(ja_content, encoding="utf-8")
        print("Japanese changelog generated.")

    if en_match:
        en_raw = en_match.group(1).strip()
        en_content = frontmatter + "# Changelog\n\n" + en_raw
        (docs_dir / "en" / "changelog.md").write_text(en_content, encoding="utf-8")
        print("English changelog generated.")


def main():
    root_dir = Path(__file__).parent.parent / "docs" / "site"
    ja_dir, en_dir = root_dir, root_dir / "en"
    for d in [ja_dir, en_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    from nyansqlite import NyanSQLite

    (ja_dir / "api.md").write_text(
        generate_class_md(NyanSQLite, "NyanSQLite API リファレンス", "PydanticネイティブなSQLiteラッパー NyanSQLite クラスのドキュメントです。", "ja"),
        encoding="utf-8",
    )
    (en_dir / "api.md").write_text(
        generate_class_md(
            NyanSQLite, "NyanSQLite API Reference", "Complete documentation for the Pydantic-native NyanSQLite class.", "en"
        ),
        encoding="utf-8",
    )

    # Generate split changelogs
    generate_changelog_md()

    print("API docs and changelogs regenerated with NyanSQLite.")


if __name__ == "__main__":
    main()
