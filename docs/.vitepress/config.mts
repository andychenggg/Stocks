import { defineConfig } from 'vitepress'
import fs from 'fs'
import path from 'path'

function getMarkdownSidebar(dirName: string) {
  const summariesDir = path.resolve(__dirname, `../${dirName}`)
  if (!fs.existsSync(summariesDir)) {
    return []
  }
  const files = fs.readdirSync(summariesDir)

  const mdFiles = files
    .filter(f => f.endsWith('.md') && f !== 'index.md' && f !== '_sidebar.md')
    .sort((a, b) => b.localeCompare(a))

  return mdFiles.map(file => ({
    text: file.replace('.md', ''),
    link: `/${dirName}/${file}`,
  }))
}

export default defineConfig({
  title: "Stocks Summaries",
  description: "A VitePress Site for Stocks Summaries.",

  base: '/',


  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: 'serenity总结', link: '/serenity-summaries/' },
      { text: '历史总结', link: '/summaries/' },
      { text: '经验总结', link: '/trading-experiences/' },
      { text: '币预警（Beta）', link: '/alerts/' }
    ],

    sidebar: {
      '/serenity-summaries/': [
        {
          text: 'Serenity 历史总结',
          items: getMarkdownSidebar('serenity-summaries')
        }
      ],
      '/summaries/': [
        {
          text: '历史总结',
          items: getMarkdownSidebar('summaries')
        }
      ]
    },

    search: {
      provider: 'local',
      options: {
        detailedView: true
      }
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/andychenggg/Stocks' }
    ]
  }
})
