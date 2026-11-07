<template>
  <div class="app-shell" :class="{ 'app-shell-map': $route.name === 'flood-map' }">
    <aside class="sidebar">
      <RouterLink class="brand" to="/" aria-label="SipatAI map">
        <span class="brand-mark">S</span>
        <span><strong>SipatAI</strong><small>FLOOD ASSESSMENT</small></span>
      </RouterLink>
      <nav class="primary-nav" aria-label="Main navigation">
        <RouterLink to="/" exact-active-class="is-active">Explore map</RouterLink>
        <RouterLink to="/dashboard" active-class="is-active">Dashboard</RouterLink>
        <RouterLink to="/scenes" active-class="is-active">Satellite scenes</RouterLink>
        <RouterLink to="/reports" active-class="is-active">Report center</RouterLink>
      </nav>
      <div class="sidebar-footer">Agricultural damage monitoring</div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div class="mobile-brand"><span class="brand-mark">S</span><strong>SipatAI</strong></div>
        <span class="environment-label"><i></i> AGRICULTURAL FLOOD ASSESSMENT</span>
        <nav class="mobile-nav" aria-label="Main navigation">
          <RouterLink to="/" exact-active-class="is-active">Map</RouterLink>
          <RouterLink to="/dashboard" active-class="is-active">Dashboard</RouterLink>
          <RouterLink to="/scenes" active-class="is-active">Scenes</RouterLink>
          <RouterLink to="/reports" active-class="is-active">Reports</RouterLink>
        </nav>
      </header>
      <RouterView />
    </main>
  </div>
</template>
