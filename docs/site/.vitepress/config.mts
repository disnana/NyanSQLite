import { defineConfig } from 'vitepress'

export default defineConfig({
    title: "NyanSQLite",
    description: "Pydantic-native SQLite wrapper for Python",
    base: '/',
    head: [
        ['link', { rel: 'icon', href: '/logo.svg' }]
    ],
    themeConfig: {
        logo: '/logo.svg',
        nav: [
            { text: 'ホーム', link: '/' },
            { text: 'ガイド', link: '/guide' },
            { text: 'APIリファレンス', link: '/api' }
        ],
        sidebar: [
            {
                text: 'はじめに',
                items: [
                    { text: '導入ガイド', link: '/guide' },
                    { text: 'チュートリアル', link: '/tutorial' },
                    { text: '変更履歴', link: '/changelog' }
                ]
            },
            {
                text: '基本機能',
                items: [
                    { text: 'バリデーション', link: '/validation' },
                    { text: 'トランザクション', link: '/transactions' },
                    { text: '非同期サポート', link: '/async' },
                    { text: 'エラーハンドリング', link: '/error_handling' }
                ]
            },
            {
                text: '運用・セキュリティ',
                items: [
                    { text: '暗号化 (計画中)', link: '/encryption' },
                    { text: 'ベストプラクティス', link: '/best_practices' },
                    { text: '例外クラス', link: '/exceptions' }
                ]
            },
            {
                text: 'APIリファレンス',
                items: [
                    { text: 'NyanSQLite API', link: '/api' }
                ]
            }
        ],
        socialLinks: [
            { icon: 'github', link: 'https://github.com/disnana/NyanSQLite' }
        ]
    },
    locales: {
        root: {
            label: '日本語',
            lang: 'ja-JP'
        },
        en: {
            label: 'English',
            lang: 'en-US',
            link: '/en/',
            themeConfig: {
                nav: [
                    { text: 'Home', link: '/en/' },
                    { text: 'Guide', link: '/en/guide' },
                    { text: 'API Reference', link: '/en/api' }
                ],
                sidebar: [
                    {
                        text: 'Getting Started',
                        items: [
                            { text: 'Tutorial Guide', link: '/en/guide' },
                            { text: 'Step-by-Step Tutorial', link: '/en/tutorial' },
                            { text: 'Changelog', link: '/en/changelog' }
                        ]
                    },
                    {
                        text: 'Core Features',
                        items: [
                            { text: 'Validation', link: '/en/validation' },
                            { text: 'Transactions', link: '/en/transactions' },
                            { text: 'Async Support', link: '/en/async' },
                            { text: 'Error Handling', link: '/en/error_handling' }
                        ]
                    },
                    {
                        text: 'Operations & Security',
                        items: [
                            { text: 'Encryption (Planned)', link: '/en/encryption' },
                            { text: 'Best Practices', link: '/en/best_practices' },
                            { text: 'Exceptions', link: '/en/exceptions' }
                        ]
                    },
                    {
                        text: 'API Reference',
                        items: [
                            { text: 'NyanSQLite API', link: '/en/api' }
                        ]
                    }
                ]
            }
        }
    }
})
