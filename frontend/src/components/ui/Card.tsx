import React from "react";
import clsx from "clsx";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  hover = false,
  glow = false,
  ...props
}) => {
  return (
    <div
      className={clsx(
        "rounded-2xl border border-dark-400/50 bg-dark-700/80 backdrop-blur-sm p-6",
        hover && "transition-all duration-300 hover:border-primary-500/30 hover:shadow-lg hover:shadow-primary-500/5 hover:-translate-y-0.5",
        glow && "ring-1 ring-primary-500/20",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
};
