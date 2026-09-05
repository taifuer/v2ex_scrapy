import './assets/main.css'

import { createApp } from 'vue'
import App from './App.vue'
import { installReleaseRecovery } from './services/releaseState'

installReleaseRecovery()
createApp(App).mount('#app')
