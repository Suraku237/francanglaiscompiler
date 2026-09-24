import './brand.css'

export function Brand({ account = false }: { account?: boolean }) {
  return <a className={`brand${account ? ' brand-auth' : ''}`} href={account ? '#signin' : '#compiler'} aria-label={`Camfranglais home, ${account ? 'sign in' : 'Franc Analyzer'}`}>
    <img className="brand-logo" src="/camfranglais-logo.png" width={48} height={48} alt="" />
    <span className="brand-word">Camfranglais</span>
  </a>
}
