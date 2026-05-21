import { defineConfig } from 'vitepress'
import fs from 'fs'
import path from 'path'

// 自动生成 summaries 列表
function getSummariesSidebar() {
  const summariesDir = path.resolve(__dirname, '../summaries')
  const files = fs.readdirSync(summariesDir)

  // 过滤并按时间倒序排序
  const mdFiles = files
    .filter(f => f.endsWith('.md') && f !== '_sidebar.md')
    .sort((a, b) => b.localeCompare(a))  // 日期倒序

  return mdFiles.map(file => ({
    text: file.replace('.md', ''),
    link: `/summaries/${file}`,
  }))
}

export default defineConfig({
  title: "Stocks Summaries",
  description: "A VitePress Site for Stocks Summaries.",

  base: '/',


  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: '历史总结', link: '/summaries/' },
      { text: '经验总结', link: '/trading-experiences/' },
      { text: '币预警（Beta）', link: '/alerts/' }
    ],

    // 🔥 侧边栏：只有 summaries 才需要
    sidebar: {
      '/summaries/': [
        {
          text: '历史总结',
          items: getSummariesSidebar()
        }
      ]
      // 首页 / 不需要 sidebar，因此不写 '/'
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
