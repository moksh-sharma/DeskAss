import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  type ReactNode,
} from "react";
import Lenis from "lenis";

export type LenisScrollHandle = {
  scrollTo: (
    target: HTMLElement | string | number,
    options?: {
      offset?: number;
      immediate?: boolean;
      duration?: number;
      lerp?: number;
    },
  ) => void;
};

type LenisScrollProps = {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
};

export const LenisScroll = forwardRef<LenisScrollHandle, LenisScrollProps>(function LenisScroll(
  { children, className = "", contentClassName = "" },
  ref,
) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const lenisRef = useRef<Lenis | null>(null);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    const content = contentRef.current;
    if (!wrapper || !content) return;

    const lenis = new Lenis({
      wrapper,
      content,
      autoRaf: true,
      lerp: 0.1,
      smoothWheel: true,
      wheelMultiplier: 1,
      touchMultiplier: 1.5,
    });
    lenisRef.current = lenis;

    return () => {
      lenis.destroy();
      lenisRef.current = null;
    };
  }, []);

  useImperativeHandle(ref, () => ({
    scrollTo(target, options) {
      lenisRef.current?.scrollTo(target, options);
    },
  }));

  return (
    <div ref={wrapperRef} className={`lenis-scroll overflow-hidden ${className}`}>
      <div ref={contentRef} className={contentClassName}>
        {children}
      </div>
    </div>
  );
});
