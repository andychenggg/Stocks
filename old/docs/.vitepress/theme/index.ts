import DefaultTheme from 'vitepress/theme'
import AlertDashboard from './components/AlertDashboard.vue'

export default {
  ...DefaultTheme,
  enhanceApp({ app }) {
    app.component('AlertDashboard', AlertDashboard)
  }
}
