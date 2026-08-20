import { BrainMark } from "@/components/ui/BrainMark";

export default function Loading() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh]">
      <div className="relative w-16 h-16">
        {/* Outer spinning ring */}
        <div className="absolute inset-0 rounded-full border-4 border-dark-600 border-t-primary-500 animate-spin" />
        {/* Inner pulsing logo */}
        <div className="absolute inset-0 flex items-center justify-center">
          <BrainMark
            className="w-7 h-7 animate-pulse"
            glow="sm"
            gradientId="brainGradientLoad"
            strokeWidth={1.8}
            nodes={false}
          />
        </div>
      </div>
      <p className="text-sm font-medium text-dark-300 mt-6 animate-pulse">
        Loading MemoryVerse…
      </p>
    </div>
  );
}
