import React from 'react'
import ReactDOM from 'react-dom/client'
import AuthGate from './AuthGate'
import './styles.css'
import './workspace.css'
import './account.css'

const root = document.getElementById('root')
if (!root) throw new Error('The application root was not found.')

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <AuthGate />
  </React.StrictMode>,
)
