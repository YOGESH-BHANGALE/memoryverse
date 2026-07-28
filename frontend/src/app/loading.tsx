export default function Loading() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh]">
      <div className="relative w-16 h-16">
        {/* Outer spinning ring */}
        <div className="absolute inset-0 rounded-full border-4 border-dark-600 border-t-primary-500 animate-spin" />
        {/* Inner pulsing logo */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xl font-bold bg-gradient-to-br from-primary-400 to-accent-400 bg-clip-text text-transparent animate-pulse">
            M
          </span>
        </div>
      </div>
      <p className="text-sm font-medium text-dark-300 mt-6 animate-pulse">
        Loading MemoryVerse…
      </p>
    </div>
  );
}
