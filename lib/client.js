/**
 * cnjobs — browser half of the plugin.
 *
 * Loaded by the DSH client module loader as `<package>/client`. It contributes
 * three surfaces to the Web UI:
 *
 * - a `sidebar.panellist` row ("CN Jobs") in the left navigation, next to
 *   Plugins / Automation tasks / 账户额度;
 * - a `main` page for that panel key, which renders the generated dashboard;
 * - a `conversation.view` tab offering the same dashboard inside a session.
 *
 * Everything points at `/cnjobs/dashboard.html`, the static route the host half
 * registers over the package's generated `data/views/` tree. Nothing is fetched
 * from an external origin, and the dashboard keeps its own search, filters and
 * detail panels.
 */
window.__ModuleLoader__.load({
  id: 'cnjobs',
  factory: (require) => {
    const module = { exports: {} }
    const exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    const react = require('react')
    const h = react.createElement

    const DASHBOARD_URL = '/cnjobs/dashboard.html'
    const PANEL_KEY = 'cnjobs'
    const LABEL = 'CN Jobs'

    /** Sidebar glyph: a bar chart, sized by the panel-list contract. */
    function ChartIcon(props) {
      const size = typeof props.size === 'number' ? props.size : 16
      const active = props.active === true
      return h(
        'svg',
        {
          width: size,
          height: size,
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          strokeWidth: active ? 2.1 : 1.8,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
          'aria-hidden': 'true',
          focusable: 'false',
          style: { display: 'block', opacity: active ? 1 : 0.85 },
        },
        h('path', { d: 'M4 20V10' }),
        h('path', { d: 'M10 20V4' }),
        h('path', { d: 'M16 20v-7' }),
        h('path', { d: 'M22 20H2' }),
      )
    }

    /** Full-height page: the generated dashboard fills the main column. */
    function DashboardPage() {
      return h(
        'div',
        {
          style: {
            display: 'flex',
            flex: '1 1 auto',
            minWidth: 0,
            minHeight: 0,
            background: '#0e1111',
          },
        },
        h('iframe', {
          src: DASHBOARD_URL,
          title: 'CN Jobs dashboard',
          style: { border: 0, width: '100%', height: '100%', background: '#0e1111' },
        }),
      )
    }

    /** Conversation tab variant of the same dashboard. */
    function DashboardView() {
      return h(
        'div',
        { style: { display: 'flex', flex: '1 1 auto', minHeight: 0, minWidth: 0 } },
        h('iframe', {
          src: DASHBOARD_URL,
          title: 'CN Jobs dashboard',
          style: { border: 0, width: '100%', height: '100%', background: '#0e1111' },
        }),
      )
    }

    function apply(ctx) {
      // Left navigation row: clicking it routes the main column to this panel.
      ctx.slots.inject('sidebar.panellist', () => {
        return ctx.slots.register(
          { name: 'sidebar.panellist', id: PANEL_KEY, order: 40, label: () => LABEL },
          (props) => h(ChartIcon, props),
        )
      })

      // The routed page for that panel key.
      ctx.slots.inject('main', () => {
        return ctx.slots.register(
          { name: 'main', key: PANEL_KEY },
          () => h(DashboardPage, null),
        )
      })

      // Right of Chat (0), Trajectory (10) and Context (20).
      ctx.slots.inject('conversation.view', () => {
        return ctx.slots.register(
          { name: 'conversation.view', id: 'cnjobs-dashboard', order: 30, label: () => LABEL },
          (props) => h(DashboardView, props),
        )
      })
    }

    module.exports = {
      name: 'cnjobs',
      inject: ['slots'],
      apply,
    }
    return module.exports
  },
})
