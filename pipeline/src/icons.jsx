import React from 'react'

function Svg({ size = 18, children, className = '', viewBox = '0 0 24 24' }) {
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export function FileIcon(props) {
  return (
    <Svg {...props}>
      <path d="M6 3.5h8l5 5v12H6z" />
      <path d="M14 3.5v5h5" />
      <path d="M9 13h6M9 16.5h4" />
    </Svg>
  )
}

export function MergeIcon(props) {
  return (
    <Svg {...props}>
      <rect x="3" y="3.5" width="7" height="6.5" rx="1.6" />
      <rect x="14" y="3.5" width="7" height="6.5" rx="1.6" />
      <path d="M12 10.5v3.5" />
      <path d="M9.6 12.2 12 14.6l2.4-2.4" />
      <rect x="5.5" y="16" width="13" height="4.5" rx="1.6" />
    </Svg>
  )
}

export function CleanIcon(props) {
  return (
    <Svg {...props}>
      <rect x="4" y="3" width="13.5" height="17" rx="2" />
      <path d="M7 9.5h7M7 12.5h5.5M7 15.5h3.5" />
      <path d="m17.2 14.4.7 1.6 1.7.2-1.3 1.1.4 1.7-1.5-.9-1.5.9.4-1.7-1.3-1.1 1.7-.2z" />
    </Svg>
  )
}

export function SplitIcon(props) {
  return (
    <Svg {...props}>
      <rect x="8" y="3" width="8" height="5.5" rx="1.6" />
      <path d="M12 8.5v3" />
      <path d="M5.2 14.3c0-1.5 1.6-2.8 3.2-2.8M18.8 14.3c0-1.5-1.6-2.8-3.2-2.8" />
      <path d="M12 11.5c-3 0-6.8 1.2-6.8 3.6M12 11.5c3 0 6.8 1.2 6.8 3.6" />
      <rect x="3" y="15.5" width="4.4" height="5.2" rx="1.2" />
      <rect x="9.8" y="15.5" width="4.4" height="5.2" rx="1.2" />
      <rect x="16.6" y="15.5" width="4.4" height="5.2" rx="1.2" />
    </Svg>
  )
}

export function OutputIcon(props) {
  return (
    <Svg {...props}>
      <path d="M4 7.5h6l2 2h8v10.5H4z" />
      <path d="M4 7.5V4h7l2 2h5v3.5" />
      <path d="M12 11.5v7M9.5 16l2.5 2.5L14.5 16" />
    </Svg>
  )
}

export function PlayIcon(props) {
  return (
    <Svg {...props}>
      <path d="M8 5.5v13l10-6.5z" fill="currentColor" stroke="none" />
    </Svg>
  )
}

export function StopIcon(props) {
  return (
    <Svg {...props}>
      <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />
    </Svg>
  )
}

export function TemplateIcon(props) {
  return (
    <Svg {...props}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.8" />
      <rect x="13" y="3.5" width="7.5" height="7.5" rx="1.8" />
      <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.8" />
      <path d="M16.8 13v7.5M13 16.8h7.5" />
    </Svg>
  )
}

export function SaveIcon(props) {
  return (
    <Svg {...props}>
      <path d="M5 3.5h11l3 3v14H5z" />
      <path d="M8 3.5V9h7V3.5M8 20.5v-6h8v6" />
    </Svg>
  )
}

export function PlusIcon(props) {
  return (
    <Svg {...props}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  )
}

export function TrashIcon(props) {
  return (
    <Svg {...props}>
      <path d="M4.5 6.5h15M9 3.5h6M7 6.5l.8 14h8.4l.8-14M10 10v7M14 10v7" />
    </Svg>
  )
}

export function CloseIcon(props) {
  return (
    <Svg {...props}>
      <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
    </Svg>
  )
}

export function ChevronIcon(props) {
  return (
    <Svg {...props}>
      <path d="m9 5.5 6.5 6.5L9 18.5" />
    </Svg>
  )
}

export function SparkIcon(props) {
  return (
    <Svg {...props}>
      <path d="m12 3 1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z" />
      <path d="m18.5 15 .8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
    </Svg>
  )
}

export function TableIcon(props) {
  return (
    <Svg {...props}>
      <rect x="3.5" y="4" width="17" height="16" rx="2" />
      <path d="M3.5 9h17M3.5 14h17M9 9v11M15 9v11" />
    </Svg>
  )
}

export function UploadIcon(props) {
  return (
    <Svg {...props}>
      <path d="M12 16V4.5M8 8.5 12 4.5l4 4M4.5 15v4h15v-4" />
    </Svg>
  )
}

export function CheckIcon(props) {
  return (
    <Svg {...props}>
      <path d="m5 12.5 4.5 4.5L19 6.5" />
    </Svg>
  )
}

export function AlertIcon(props) {
  return (
    <Svg {...props}>
      <path d="M12 3.5 21 20H3z" />
      <path d="M12 9v5M12 17.2v.1" />
    </Svg>
  )
}

export function FolderIcon(props) {
  return (
    <Svg {...props}>
      <path d="M3.5 7h6l2 2h8.5v10.5h-16.5z" />
      <path d="M3.5 7V4.5h7l2 2h5V7" />
    </Svg>
  )
}

export function SettingsIcon(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6 18 18M18 6l-1.4 1.4M7.4 16.6 6 18" />
    </Svg>
  )
}

export function EyeIcon(props) {
  return (
    <Svg {...props}>
      <path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.6" />
    </Svg>
  )
}

export function LogIcon(props) {
  return (
    <Svg {...props}>
      <path d="M4 4.5h16v15H4z" />
      <path d="M7.5 9h9M7.5 12h9M7.5 15h5" />
    </Svg>
  )
}

export function FitIcon(props) {
  return (
    <Svg {...props}>
      <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
    </Svg>
  )
}

export function HelpIcon(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M9.4 9.2a2.8 2.8 0 1 1 4.2 2.4c-.9.5-1.6 1-1.6 2.1" />
      <path d="M12 17.1v.1" />
    </Svg>
  )
}

export function GripIcon(props) {
  return (
    <Svg {...props}>
      <circle cx="9" cy="7" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="7" r="1" fill="currentColor" stroke="none" />
      <circle cx="9" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="9" cy="17" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="17" r="1" fill="currentColor" stroke="none" />
    </Svg>
  )
}

export function FlowIcon(props) {
  return (
    <Svg {...props}>
      <rect x="3" y="4" width="6" height="5" rx="1.4" />
      <rect x="15" y="3.5" width="6" height="6" rx="1.4" />
      <rect x="9" y="15.5" width="6" height="5" rx="1.4" />
      <path d="M6 9v3.5h12V9.5M12 12.5v3" />
    </Svg>
  )
}
