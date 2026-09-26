import './brand.css'

export function Brand() {
  return <a className="brand" href="#compiler" aria-label="Camfranglais home, Franc Analyzer">
    <img className="brand-logo" src="/camfranglais-logo.png" width={48} height={48} alt="" />
    <span className="brand-word">Camfranglais</span>
  </a>
}
