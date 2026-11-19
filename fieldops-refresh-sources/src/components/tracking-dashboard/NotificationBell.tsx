import React from 'react';
import { useNotificationStore } from '../../store/notificationStore';

export const NotificationBell: React.FC = () => {
  const { alerts, isPanelOpen, setPanelOpen } = useNotificationStore();
  const unreadCount = alerts.filter((a) => !a.isRead).length;

  return (
    <button
      onClick={() => setPanelOpen(!isPanelOpen)}
      className="relative p-2 text-slate-600 hover:text-slate-900 focus:outline-none transition-all rounded-full hover:bg-slate-100/80 active:scale-95"
      aria-label={`Geofence alerts, ${unreadCount} unread`}
      data-testid="notification-bell"
    >
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"
        />
      </svg>
      {unreadCount > 0 && (
        <span
          className="absolute top-1.5 right-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 text-[10px] font-bold leading-none text-white bg-rose-500 rounded-full ring-2 ring-white"
          data-testid="bell-badge"
        >
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  );
};

export default NotificationBell;
