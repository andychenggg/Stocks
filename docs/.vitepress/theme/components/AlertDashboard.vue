<template>
  <div class="alerts-page">
    <header class="alerts-hero">
      <div>
        <p class="eyebrow">实盘监控 · Binance</p>
        <h1>币预警</h1>
        <p class="sub">实时价格、日内涨跌幅与极速波动提醒（BTCUSDT / ETHUSDT）。</p>
      </div>
      <div class="connection" :class="connectionClass">
        <span class="dot"></span>
        <span>{{ connectionLabel }}</span>
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
          今开: <strong>{{ todayOpen(sym) ?? '--' }}</strong>
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
            {{ fmtTs(a.ts) }} | O {{ formatPrice(a.reference.open) }} · C {{ formatPrice(a.reference.close) }} · L {{ formatPrice(a.reference.low) }} · H {{ formatPrice(a.reference.high) }}
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

type PricePoint = { t: number; v: number }
type SeriesMap = Record<string, PricePoint[]>

const symbols = ['BTCUSDT', 'ETHUSDT']
const maxPoints = 240
const alerts = reactive<any[]>([])
const lastPrices = reactive<Record<string, number | null>>({
  BTCUSDT: null,
  ETHUSDT: null
})
const todayOpens = reactive<Record<string, number | null>>({
  BTCUSDT: null,
  ETHUSDT: null
})
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

symbols.forEach((sym) => {
  chartRefs[sym] = (el: HTMLElement | null) => {
    if (el) chartEls.set(sym, el)
  }
})

const connectionLabel = computedLabel()
const connectionClass = computedClass()

onMounted(async () => {
  await loadEcharts()
  initCharts()
  connect()
})

onBeforeUnmount(() => {
  cleanupWs()
  charts.forEach((c) => c?.dispose?.())
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

function handleMessage(msg: any) {
  if (msg.type === 'snapshot' && msg.data) {
    Object.entries(msg.data).forEach(([sym, payload]) => {
      const s = sym.toUpperCase()
      lastPrices[s] = payload.price ?? null
      todayOpens[s] = payload.today_open ?? null
    })
    updateCharts()
  } else if (msg.type === 'price') {
    const sym = msg.symbol
    lastPrices[sym] = msg.price ?? null
    todayOpens[sym] = msg.today_open ?? null
    pushPoint(sym, msg.ts, msg.price)
    updateCharts()
  } else if (msg.type === 'alert') {
    alerts.unshift({
      ...msg,
      id: `${msg.symbol}-${msg.alert_type}-${msg.ts}-${msg.magnitude}`
    })
    if (alerts.length > 50) alerts.pop()
  }
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
    grid: { left: 40, right: 10, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: [], boundaryGap: false, axisLabel: { show: false } },
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
  const o = todayOpens[sym]
  const p = lastPrices[sym]
  if (o === null || p === null || o === 0) return null
  return (p - o) / o
}

function lastPrice(sym: string) {
  return lastPrices[sym]
}

function todayOpen(sym: string) {
  return todayOpens[sym]
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
  const d = new Date(ts)
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

function fmtTs(ts: number) {
  const d = new Date(ts)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`
}

function pad(n: number) {
  return n.toString().padStart(2, '0')
}

function badge(type: string) {
  if (type === 'rapid_drop') return '极速下跌'
  if (type === 'rapid_rebound') return '极速反弹'
  return type
}

function buildWsUrl() {
  // 1) Highest priority: complete URL override (e.g., wss://example.com/alerts)
  const overrideUrl =
    (window as any).__ALERT_WS_URL ||
    (import.meta as any).env?.VITE_ALERT_WS_URL
  if (overrideUrl) return overrideUrl as string



  // 2) Otherwise build from scheme + host + port
  const loc = window.location
//   const wsScheme = loc.protocol === 'https:' ? 'wss' : 'ws'
    const wsScheme = 'ws';
//   const host =
//     (window as any).__ALERT_WS_HOST ||
//     (import.meta as any).env?.VITE_ALERT_WS_HOST ||
//     loc.hostname ||
//     'localhost'
    const host = 'localhost';
  const port =
    (window as any).__ALERT_WS_PORT ||
    (import.meta as any).env?.VITE_ALERT_WS_PORT ||
    CLIENT_PORT
  return `${wsScheme}://${host}:${port}`
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
}
</style>
