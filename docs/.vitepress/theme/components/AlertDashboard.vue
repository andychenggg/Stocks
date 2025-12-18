<template>
  <div class="alerts-page">
    <header class="alerts-hero">
      <div>
        <p class="eyebrow">实盘监控 · Binance</p>
        <h1>币预警</h1>
        <p class="sub">实时价格、日内涨跌幅与极速波动提醒（BTCUSDT / ETHUSDT）。</p>
      </div>
      <div class="hero-controls">
        <div class="connection" :class="connectionClass">
          <span class="dot"></span>
          <span>{{ connectionLabel }}</span>
        </div>
        <div class="tz-select">
          <label for="tz">时间</label>
          <select id="tz" v-model="selectedTz">
            <option v-for="tz in tzOptions" :key="tz.key" :value="tz.key">
              {{ tz.label }}
            </option>
          </select>
        </div>
      </div>
    </header>

    <section class="cards">
      <div v-for="sym in symbols" :key="sym" class="card">
        <div class="card-head">
          <div class="symbol">{{ sym }}</div>
          <div class="pct" :class="{ up: pct(sym) > 0, down: pct(sym) < 0 }">
            <span v-if="pct(sym) !== null">{{ formatPct(pct(sym)) }}</span>
            <span v-else>--</span>
          </div>
        </div>
        <div class="price">
          <span v-if="lastPrice(sym) !== null">{{ formatPrice(lastPrice(sym)) }}</span>
          <span v-else>--</span>
        </div>
        <div class="mini">
          今开 ({{ currentTzLabel }}): <strong>{{ todayOpen(sym) ?? '--' }}</strong>
        </div>
        <div class="chart" :ref="setChartRef(sym)"></div>
      </div>
    </section>

    <section class="alerts-list">
      <div class="alerts-head">
        <h2>实时预警</h2>
        <span class="small">最近 50 条 · 已去重</span>
      </div>
      <div v-if="alerts.length === 0" class="empty">暂无预警</div>
      <div v-else class="alert-row" v-for="a in alerts" :key="a.id">
        <div class="pill" :class="a.alert_type">{{ badge(a.alert_type) }}</div>
        <div class="text">
          <div class="title">
            {{ a.symbol }} · {{ a.magnitude * 100 }}% · {{ a.window_minutes }}m
          </div>
          <div class="meta">
            {{ anchorLabel(a) }} {{ fmtTs(anchorTs(a)) }} · {{ pctOrDash(anchorPct(a)) }} · {{ formatPrice(anchorPrice(a)) }} | 触发 {{ fmtTs(triggerTs(a)) }} · {{ pctOrDash(currentPct(a)) }} · {{ formatPrice(triggerPrice(a)) }}
          </div>
          <div class="meta">
            今开 {{ formatPrice(a.reference.open) }} · 变动 {{ pctOrDash(moveFromAnchor(a)) }}（阈值 {{ (a.magnitude * 100).toFixed(1) }}%）
          </div>
        </div>
      </div>
    </section>
    <Transition name="fade">
      <div v-if="showWelcomeModal" class="modal-backdrop">
        <div class="modal-content">
          <div class="modal-icon">🔔</div>
          <h2>开启实时监控</h2>
          <p>
            为了确保您不会错过任何行情波动，本页面需要启用<strong>音频播放</strong>与<strong>系统通知</strong>权限。
          </p>
          <div class="modal-example">
            <span>⚠️ 将在检测到异常波动时发出警报</span>
          </div>
          <button class="btn-primary" @click="enableAndEnter">
            开启警报并进入
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

type PricePoint = { t: number; v: number }
type SeriesMap = Record<string, PricePoint[]>

const symbols = ['BTCUSDT', 'ETHUSDT']
const maxPoints = 240
const alertApiUrl = buildAlertApiUrl()
const tzOptions = [
  { key: 'utc', label: 'UTC+0', timeZone: 'UTC' },
  { key: 'us_west', label: '美西 (PT)', timeZone: 'America/Los_Angeles' },
  { key: 'us_east', label: '美东 (ET)', timeZone: 'America/New_York' },
  { key: 'beijing', label: '北京时间', timeZone: 'Asia/Shanghai' }
]
const tzOptionMap = Object.fromEntries(tzOptions.map((o) => [o.key, o]))
const selectedTz = ref<string>('utc')
const alerts = reactive<any[]>([])
const lastPrices = reactive<Record<string, number | null>>({
  BTCUSDT: null,
  ETHUSDT: null
})
const dayOpens = reactive<Record<string, Record<string, number | null>>>(
  tzOptions.reduce((acc, tz) => {
    acc[tz.key] = { BTCUSDT: null, ETHUSDT: null }
    return acc
  }, {} as Record<string, Record<string, number | null>>)
)
const series: SeriesMap = reactive({
  BTCUSDT: [],
  ETHUSDT: []
})

const chartEls = new Map<string, HTMLElement>()
const chartRefs = reactive<Record<string, (el: HTMLElement | null) => void>>({})
const charts = new Map<string, any>()
let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let echartsLib: any = null
const connectionState = ref<'connecting' | 'open' | 'closed'>('connecting')
let refreshTimer: number | null = null

symbols.forEach((sym) => {
  chartRefs[sym] = (el: HTMLElement | null) => {
    if (el) chartEls.set(sym, el)
  }
})

const connectionLabel = computedLabel()
const connectionClass = computedClass()
const currentTzLabel = computed(() => tzOptionMap[selectedTz.value]?.label ?? 'UTC+0')
const showWelcomeModal = ref(true)
onMounted(async () => {
  await loadEcharts()
  initCharts()
  fetchInitialAlerts()
  connect()
})


onBeforeUnmount(() => {
  cleanupWs()
  charts.forEach((c) => c?.dispose?.())
})

watch(selectedTz, () => {
  updateCharts()
})

function computedLabel() {
  return computed(() => {
    if (connectionState.value === 'open') return '实时连接'
    if (connectionState.value === 'connecting') return '连接中'
    return '已断开，重试中'
  })
}

function computedClass() {
  return computed(() => {
    return {
      live: connectionState.value === 'open',
      connecting: connectionState.value === 'connecting',
      down: connectionState.value === 'closed'
    }
  })
}

async function loadEcharts() {
  if ((window as any).echarts) {
    echartsLib = (window as any).echarts
    return
  }
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'
    script.onload = () => {
      echartsLib = (window as any).echarts
      resolve()
    }
    script.onerror = () => reject(new Error('Failed to load ECharts'))
    document.head.appendChild(script)
  })
}

function initCharts() {
  symbols.forEach((sym) => {
    const el = chartEls.get(sym)
    if (!el || !echartsLib) return
    const chart = echartsLib.init(el)
    charts.set(sym, chart)
    chart.setOption(baseOption(sym))
  })
}

function connect() {
  const url = buildWsUrl()
  connectionState.value = 'connecting'
  ws = new WebSocket(url)
  ws.onopen = () => {
    connectionState.value = 'open'
  }
  ws.onclose = () => {
    connectionState.value = 'closed'
    scheduleReconnect()
  }
  ws.onerror = () => {
    connectionState.value = 'closed'
    scheduleReconnect()
  }
  ws.onmessage = (evt) => {
    try {
      handleMessage(JSON.parse(evt.data))
    } catch (e) {
      console.error('Bad message', e)
    }
  }
}

function cleanupWs() {
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    connect()
  }, 3000)
}

// handle sound alert 
let audio: HTMLAudioElement | null = null;
async function enableAndEnter() {
  showWelcomeModal.value = false
  playAlertSound()
  await requestAndShowTestNotification()
}
async function requestAndShowTestNotification() {
  if (!("Notification" in window)) return

  let permission = Notification.permission
  if (permission !== "granted") {
    permission = await Notification.requestPermission()
  }

  // 如果获得权限，发送一条测试通知
  if (permission === "granted") {
    new Notification("系统就绪", {
      body: "您的浏览器通知与音频警报已开启。",
      icon: "https://cryptologos.cc/logos/bitcoin-btc-logo.png" 
    })
  }
}
// 在 onMounted 中初始化（或在第一次播放时初始化）
function playAlertSound() {
  if (!audio) {
    audio = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3');
  }
  audio.currentTime = 0; 
  audio.play().catch(e => {
    console.warn('音频播放失败 (可能是因为用户尚未与页面交互)', e);
  });
}

async function showNativeNotification(msg: any) {
  // 如果浏览器不支持或用户未授权，直接返回
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;

  // 格式化数据用于显示
  const symbol = msg.symbol;
  const typeText = badge(msg.alert_type); 
  const change = moveFromAnchor(msg);
  const price = formatPrice(triggerPrice(msg));

  // 构建通知内容
  const title = `🚨 ${symbol} ${typeText}`;
  const body = `现价: ${price}\n波动: ${pctOrDash(change)} (阈值 ${(msg.magnitude * 100).toFixed(1)}%)`;

  // 发送通知
  new Notification(title, {
    body: body,
    icon: '/logo.png', 
    tag: msg.id,
    requireInteraction: true
  });
}

function handleMessage(msg: any) {
  if (msg.type === 'snapshot' && msg.data) {
    Object.entries(msg.data).forEach(([sym, payload]) => {
      const s = sym.toUpperCase()
      lastPrices[s] = payload.price ?? null
      setDayOpens(s, payload.day_open, payload.today_open)
    })
    if (Array.isArray(msg.alerts)) {
      hydrateAlerts(msg.alerts)
    }
    updateCharts()
  } else if (msg.type === 'price') {
    const sym = msg.symbol
    lastPrices[sym] = msg.price ?? null
    setDayOpens(sym, msg.day_open, msg.today_open)
    pushPoint(sym, msg.ts, msg.price)
    updateCharts()
  } else if (msg.type === 'alert') {
    const id = `${msg.symbol}-${msg.alert_type}-${msg.ts}-${msg.magnitude}`
    if (alerts.find((a) => a.id === id)) return
    const newAlert = { ...msg, id }
    alerts.unshift(newAlert)
    if (alerts.length > 50) alerts.pop()
    // scheduleRefreshOnAlert()
    playAlertSound()
    showNativeNotification(newAlert)
  }
}

async function fetchInitialAlerts() {
  if (!alertApiUrl) return
  try {
    const res = await fetch(alertApiUrl)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (Array.isArray(data.alerts)) hydrateAlerts(data.alerts)
  } catch (err) {
    console.error('Failed to fetch initial alerts', err)
  }
}

function hydrateAlerts(list: any[]) {
  alerts.splice(
    0,
    alerts.length,
    ...list.map((a) => ({
      ...a,
      id: `${a.symbol}-${a.alert_type}-${a.ts}-${a.magnitude}`
    }))
  )
}

function setDayOpens(sym: string, dayOpenMap: Record<string, number> | undefined, legacyOpen: number | null) {
  const map = dayOpenMap || { utc: legacyOpen }
  Object.entries(map).forEach(([tz, v]) => {
    if (!dayOpens[tz]) {
      dayOpens[tz] = { BTCUSDT: null, ETHUSDT: null }
    }
    dayOpens[tz][sym] = v ?? null
  })
}

function pushPoint(sym: string, ts: number, price: number) {
  const arr = series[sym]
  arr.push({ t: ts, v: price })
  if (arr.length > maxPoints) arr.shift()
}

function updateCharts() {
  charts.forEach((chart, sym) => {
    const data = series[sym] || []
    const times = data.map((p) => fmtTime(p.t))
    const prices = data.map((p) => p.v)
    chart.setOption({
      xAxis: { data: times },
      series: [{ data: prices }]
    })
  })
}

function baseOption(sym: string) {
  return {
    title: { text: sym, left: 'center', textStyle: { fontSize: 12 } },
    tooltip: { trigger: 'axis' },
    grid: { left: 64, right: 16, top: 30, bottom: 40, containLabel: true },
    xAxis: {
      type: 'category',
      data: [],
      boundaryGap: false,
      axisLabel: { show: true, margin: 12, hideOverlap: true }
    },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        type: 'line',
        data: [],
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2 }
      }
    ]
  }
}

function pct(sym: string) {
  const o = todayOpen(sym)
  const p = lastPrices[sym]
  if (o === null || p === null || o === 0) return null
  return (p - o) / o
}

function lastPrice(sym: string) {
  return lastPrices[sym]
}

function todayOpen(sym: string) {
  const tz = selectedTz.value
  if (!dayOpens[tz]) return null
  return dayOpens[tz][sym]
}

function formatPrice(v: number | null) {
  if (v === null || v === undefined) return '--'
  if (v >= 1000) return v.toFixed(1)
  if (v >= 10) return v.toFixed(2)
  return v.toFixed(4)
}

function formatPct(v: number) {
  return `${(v * 100).toFixed(2)}%`
}

function fmtTime(ts: number) {
  return formatWithTz(ts, { hour: '2-digit', minute: '2-digit' })
}

function fmtTs(ts: number) {
  return formatWithTz(ts, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function formatWithTz(ts: number, opts: Intl.DateTimeFormatOptions) {
  const tzKey = selectedTz.value
  const tz = tzOptionMap[tzKey]?.timeZone || 'UTC'
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: tz,
    ...opts,
    hour12: false
  }).format(new Date(ts))
}

function badge(type: string) {
  if (type === 'rapid_drop') return '极速下跌'
  if (type === 'rapid_rebound') return '极速反弹'
  return type
}

function peakPrice(a: any) {
  return a?.reference?.peak_price ?? a?.reference?.high ?? null
}

function pctOrDash(v: number | null | undefined) {
  if (v === null || v === undefined) return '--'
  return formatPct(v)
}

function anchorPrice(a: any) {
  return a?.reference?.anchor_price ?? a?.reference?.peak_price ?? a?.reference?.high ?? null
}

function anchorTs(a: any) {
  return a?.reference?.anchor_ts ?? a?.reference?.peak_ts ?? a?.ts ?? null
}

function anchorPct(a: any) {
  if (a?.reference?.anchor_pct_from_open !== undefined && a?.reference?.anchor_pct_from_open !== null) {
    return a.reference.anchor_pct_from_open
  }
  const open = a?.reference?.open
  const anchor = anchorPrice(a)
  if (open === null || open === undefined || open === 0 || anchor === null) return null
  return (anchor - open) / open
}

function currentPct(a: any) {
  if (a?.reference?.current_pct_from_open !== undefined && a?.reference?.current_pct_from_open !== null) {
    return a.reference.current_pct_from_open
  }
  const open = a?.reference?.open
  const current = triggerPrice(a)
  if (open === null || open === undefined || open === 0 || current === null) return null
  return (current - open) / open
}

function triggerPrice(a: any) {
  return a?.reference?.current_price ?? a?.reference?.close ?? null
}

function triggerTs(a: any) {
  return a?.reference?.current_ts ?? a?.ts ?? null
}

function moveFromAnchor(a: any) {
  if (a?.reference?.move_from_anchor !== undefined && a?.reference?.move_from_anchor !== null) {
    return a.reference.move_from_anchor
  }
  if (a?.alert_type === 'rapid_drop') return a?.reference?.drop_from_peak ?? null
  if (a?.alert_type === 'rapid_rebound') return a?.reference?.rise_from_trough ?? null
  return null
}

function anchorLabel(a: any) {
  if (a?.reference?.anchor_type === 'trough') return '低点'
  if (a?.alert_type === 'rapid_rebound') return '低点'
  return '高点'
}

function scheduleRefreshOnAlert() {
  if (refreshTimer) return
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null
    window.location.reload()
  }, 300)
}

function buildWsUrl() {
  return `wss://ws.flowbyte.me`
}

function buildAlertApiUrl() {
  const ws = buildWsUrl()
  if (ws.startsWith('wss://')) return ws.replace('wss://', 'https://') + '/alerts/recent'
  if (ws.startsWith('ws://')) return ws.replace('ws://', 'http://') + '/alerts/recent'
  return ''
}


const CLIENT_PORT = 8765

function setChartRef(sym: string) {
  return (el: HTMLElement | null) => {
    chartRefs[sym]?.(el)
    if (el && echartsLib) {
      // re-init if needed (e.g., hot reload)
      const chart = charts.get(sym)
      if (!chart) {
        const instance = echartsLib.init(el)
        charts.set(sym, instance)
        instance.setOption(baseOption(sym))
      }
    }
  }
}
</script>

<style scoped>
.alerts-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 12px 0 32px;
}

.alerts-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(0, 178, 255, 0.08), rgba(0, 255, 170, 0.08));
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-2);
  margin: 0 0 4px;
}

h1 {
  margin: 0 0 6px;
  font-size: 28px;
  line-height: 1.2;
}

.sub {
  margin: 0;
  color: var(--vp-c-text-2);
}

.hero-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.connection {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 14px;
  border: 1px solid var(--vp-c-divider);
}
.connection .dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--vp-c-text-3);
}
.connection.live .dot {
  background: #16c784;
  box-shadow: 0 0 0 6px rgba(22, 199, 132, 0.15);
}
.connection.connecting .dot {
  background: #f5a524;
}
.connection.down .dot {
  background: #ef4444;
}

.tz-select {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  padding: 6px 8px;
  font-size: 14px;
  background: var(--vp-c-bg);
}
.tz-select label {
  color: var(--vp-c-text-2);
}
.tz-select select {
  border: none;
  background: transparent;
  font-size: 14px;
  outline: none;
  padding: 2px 4px;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.card {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 12px;
  background: var(--vp-c-bg-soft);
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.symbol {
  font-weight: 700;
  letter-spacing: 0.04em;
}

.pct {
  font-weight: 600;
}
.pct.up {
  color: #16c784;
}
.pct.down {
  color: #ef4444;
}

.price {
  font-size: 24px;
  font-weight: 700;
  margin: 8px 0 2px;
}

.mini {
  color: var(--vp-c-text-2);
  font-size: 13px;
}

.chart {
  margin-top: 10px;
  width: 100%;
  height: 180px;
}

.alerts-list {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 12px;
}

.alerts-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.small {
  color: var(--vp-c-text-2);
  font-size: 13px;
}

.alert-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-top: 1px solid var(--vp-c-divider);
}
.alert-row:first-of-type {
  border-top: none;
}

.pill {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
}
.pill.rapid_drop {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.3);
}
.pill.rapid_rebound {
  color: #16c784;
  border-color: rgba(22, 199, 132, 0.3);
}

.title {
  font-weight: 700;
}
.meta {
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.empty {
  padding: 12px;
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .alerts-hero {
    flex-direction: column;
    align-items: flex-start;
  }
  .hero-controls {
    width: 100%;
    justify-content: space-between;
  }
}

/* --- 弹窗样式 --- */
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px); /* 背景磨砂模糊 */
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-content {
  background: var(--vp-c-bg); /* 使用现有变量，或改为 #1e1e20 */
  border: 1px solid var(--vp-c-divider);
  padding: 32px;
  border-radius: 24px;
  width: 90%;
  max-width: 400px;
  text-align: center;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  align-items: center;
  animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.modal-icon {
  font-size: 48px;
  margin-bottom: 16px;
  background: var(--vp-c-bg-soft);
  width: 80px;
  height: 80px;
  line-height: 80px;
  border-radius: 50%;
  border: 1px solid var(--vp-c-divider);
}

.modal-content h2 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 12px;
  background: linear-gradient(120deg, #16c784, #00b2ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.modal-content p {
  color: var(--vp-c-text-2);
  font-size: 15px;
  line-height: 1.6;
  margin-bottom: 24px;
}

.modal-example {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #ef4444;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 24px;
}

.btn-primary {
  background: linear-gradient(90deg, #16c784, #0caadc);
  color: white;
  border: none;
  padding: 12px 32px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 99px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(22, 199, 132, 0.3);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(22, 199, 132, 0.4);
}

.btn-primary:active {
  transform: translateY(0);
}

/* 动画效果 */
@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
