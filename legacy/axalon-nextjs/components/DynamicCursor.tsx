import dynamic from 'next/dynamic'

const Cursor = dynamic(() => import('./UI/Cursor'), { ssr: false })
export default Cursor
