import DefaultTheme from 'vitepress/theme'
import AlertDashboard from './components/AlertDashboard.vue'
import './style.css'

export default {
  ...DefaultTheme,
  enhanceApp({ app }) {
    app.component('AlertDashboard', AlertDashboard)
  }
}
