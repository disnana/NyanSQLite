---
layout: home

hero:
  name: "NyanSQLite"
  text: "Pydantic-native SQLite Wrapper"
  tagline: "Pydantic models as database schemas.<br>Type-safe, High-performance, Full-text search enabled."
  image:
    src: /logo.svg
    alt: NyanSQLite Logo
  actions:
    - theme: brand
      text: Get Started
      link: /en/guide
    - theme: alt
      text: GitHub
      link: https://github.com/disnana/NyanSQLite

features:
  - title: "Pydantic Native"
    details: "Automatically generate tables by registering Pydantic models. Use type hints directly as your schema."
  - title: "Type-safe Validation"
    details: "Pydantic's powerful validation runs automatically on inserts and updates, ensuring data integrity."
  - title: "Django-like Queries"
    details: "Intuitive keywords like `name__like` or `age__gt` for complex searches without writing SQL."
  - title: "Fast Full-text Search"
    details: "Built-in FTS5 support. Enable rapid text search by simply adding the `Searchable` annotation."
  - title: "Auto Serialization"
    details: "Transparently store and retrieve complex types like lists, dicts, datetime, and Enums via automatic JSON serialization."
  - title: "Comprehensive Docs"
    details: "Bilingual (EN/JA) documentation covering everything from tutorials to best practices."
---
