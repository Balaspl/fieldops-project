import React from 'react';
import { MarkerF } from '@react-google-maps/api';

interface JobSiteMarkerProps {
  job: {
    job_id: string;
    latitude: number;
    longitude: number;
    status: string;
  };
  onClick: () => void;
}

export const JobSiteMarker: React.FC<JobSiteMarkerProps> = ({ job, onClick }) => {
  const getJobMarkerIcon = (status: string) => {
    const s = (status || '').toUpperCase();
    let fillColor = '#3B82F6'; // Default Blue

    if (s === 'QUEUED') {
      fillColor = '#64748B'; // Slate
    } else if (s === 'ASSIGNED') {
      fillColor = '#3B82F6'; // Blue
    } else if (s === 'EN_ROUTE') {
      fillColor = '#10B981'; // Green
    } else if (s === 'ON_SITE') {
      fillColor = '#F59E0B'; // Orange
    }

    return {
      path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
      fillColor,
      fillOpacity: 1.0,
      strokeColor: '#FFFFFF',
      strokeWeight: 2.5,
      scale: 1.3,
      anchor: typeof google !== 'undefined' ? new google.maps.Point(12, 22) : undefined,
    };
  };

  return (
    <MarkerF
      position={{ lat: job.latitude, lng: job.longitude }}
      onClick={onClick}
      icon={getJobMarkerIcon(job.status)}
      title={`Job Site: ${job.job_id}`}
    />
  );
};

export default JobSiteMarker;
