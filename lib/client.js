/**
 * cnjobs — browser half of the plugin.
 *
 * Loaded by the DSH client module loader as `<package>/client`. It contributes
 * two surfaces to the Web UI:
 *
 * - a `conversation.view` tab that renders the generated dashboard in place;
 * - a `sidebar.footer.action` row that opens the same dashboard full page.
 *
 * Both point at `/cnjobs/dashboard.html`, the static route the host half
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
    const TAB_LABEL = 'CN Jobs'

    /** Conversation-area tab: the dashboard fills the view. */
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

    /** Sidebar footer row: open the dashboard as a full page. */
    function OpenDashboardButton(props) {
      const wide = props !== null && props !== undefined && props.wide === true
      return h(
        'button',
        {
          type: 'button',
          title: 'Open the CN Jobs dashboard',
          onClick: () => window.open(DASHBOARD_URL, '_blank', 'noopener'),
          style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: wide ? 'flex-start' : 'center',
            gap: 8,
            width: '100%',
            padding: wide ? '6px 10px' : '6px',
            border: '1px solid transparent',
            borderRadius: 8,
            background: 'transparent',
            color: 'inherit',
            font: 'inherit',
            cursor: 'pointer',
          },
        },
        h('span', { 'aria-hidden': true, style: { fontSize: 14, lineHeight: 1 } }, '📊'),
        wide ? h('span', null, TAB_LABEL) : null,
      )
    }

    function apply(ctx) {
      ctx.slots.inject('conversation.view', () => {
        return ctx.slots.register(
          // Right of Chat (0), Trajectory (10) and Context (20).
          { name: 'conversation.view', id: 'cnjobs-dashboard', order: 30, label: () => TAB_LABEL },
          (props) => h(DashboardView, props),
        )
      })
      ctx.slots.inject('sidebar.footer.action', () => {
        return ctx.slots.register(
          { name: 'sidebar.footer.action', id: 'cnjobs-open', order: 10 },
          (props) => h(OpenDashboardButton, props),
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
