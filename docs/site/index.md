---
layout: home

hero:
  name: "NyanSQLite"
  text: "Pydanticネイティブ SQLiteラッパー"
  tagline: "Pydanticモデルをそのままデータベーススキーマに。<br>型安全、高性能、全文検索対応。"
  image:
    src: /logo.svg
    alt: NyanSQLite Logo
  actions:
    - theme: brand
      text: 今すぐ始める
      link: /guide
    - theme: alt
      text: GitHub
      link: https://github.com/disnana/NyanSQLite

features:
  - title: "Pydanticネイティブ"
    details: "Pydanticモデルを登録するだけでテーブルを自動生成。型ヒントをそのままスキーマとして活用できます。"
  - title: "型安全なバリデーション"
    details: "データの挿入・更新時にPydanticの強力なバリデーションが自動実行され、データの整合性を保証します。"
  - title: "Djangoライクなクエリ"
    details: "SQLを書かずに `name__like` や `age__gt` といった直感的なキーワード引数で複雑な検索が可能です。"
  - title: "高性能な全文検索"
    details: "SQLiteのFTS5をサポート。`Searchable` アノテーションを付けるだけで高速なテキスト検索を導入できます。"
  - title: "自動シリアライズ"
    details: "リストや辞書、datetime、Enumなどの複雑な型も自動的にJSONシリアライズして透過的に保存・取得できます。"
  - title: "充実したドキュメント"
    details: "日本語・英語のバイリンガルドキュメント。チュートリアルからベストプラクティスまで網羅しています。"
---
