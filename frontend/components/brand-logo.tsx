interface BrandLogoProps {
  className?: string;
}

/** Chrome-gradient "H" monogram, styled after the Novalantis "N" mark (diagonal
 * blue-to-silver metallic ribbon with a gloss highlight sweep). */
export function BrandLogo({ className }: BrandLogoProps) {
  return (
    <svg
      viewBox="0 0 100 100"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Hireonomous"
    >
      <defs>
        <linearGradient id="hireonomous-logo-chrome" x1="0" y1="0" x2="100" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0a2647" />
          <stop offset="22%" stopColor="#1a4a85" />
          <stop offset="40%" stopColor="#3d78bf" />
          <stop offset="50%" stopColor="#a9c6e6" />
          <stop offset="60%" stopColor="#4a6d95" />
          <stop offset="80%" stopColor="#243c56" />
          <stop offset="100%" stopColor="#0f1e2e" />
        </linearGradient>
        <linearGradient id="hireonomous-logo-highlight" x1="0" y1="0" x2="100" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="46%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="50%" stopColor="#ffffff" stopOpacity=".85" />
          <stop offset="54%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>

      <path
        d="M 18 8 C 27 8, 33 14.5, 33 23 L 33 77 C 33 85.5, 27 92, 18 92 C 24.5 92, 29 87, 29 79 L 29 21 C 29 13, 24.5 8, 18 8 Z"
        fill="url(#hireonomous-logo-chrome)"
        stroke="#0a1c30"
        strokeWidth="0.6"
      />
      <path
        d="M 82 8 C 73 8, 67 14.5, 67 23 L 67 77 C 67 85.5, 73 92, 82 92 C 75.5 92, 71 87, 71 79 L 71 21 C 71 13, 75.5 8, 82 8 Z"
        fill="url(#hireonomous-logo-chrome)"
        stroke="#0a1c30"
        strokeWidth="0.6"
      />
      <path
        d="M 29 43 C 40 49, 60 49, 71 43 L 71 57 C 60 63, 40 63, 29 57 Z"
        fill="url(#hireonomous-logo-chrome)"
        stroke="#0a1c30"
        strokeWidth="0.6"
      />

      <path
        d="M 18 8 C 27 8, 33 14.5, 33 23 L 33 77 C 33 85.5, 27 92, 18 92 C 24.5 92, 29 87, 29 79 L 29 21 C 29 13, 24.5 8, 18 8 Z"
        fill="url(#hireonomous-logo-highlight)"
      />
      <path
        d="M 82 8 C 73 8, 67 14.5, 67 23 L 67 77 C 67 85.5, 73 92, 82 92 C 75.5 92, 71 87, 71 79 L 71 21 C 71 13, 75.5 8, 82 8 Z"
        fill="url(#hireonomous-logo-highlight)"
      />
      <path
        d="M 29 43 C 40 49, 60 49, 71 43 L 71 57 C 60 63, 40 63, 29 57 Z"
        fill="url(#hireonomous-logo-highlight)"
      />
    </svg>
  );
}
