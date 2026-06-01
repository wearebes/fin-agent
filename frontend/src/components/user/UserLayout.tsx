import { Outlet } from 'react-router-dom'
import UserSidebar from './UserSidebar'

export default function UserLayout() {
  return (
    <div className="user-layout">
      <UserSidebar />
      <main className="user-main">
        <Outlet />
      </main>
    </div>
  )
}
