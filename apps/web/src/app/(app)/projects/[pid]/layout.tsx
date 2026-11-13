import { ProjectGate } from "@/features/projects/components/project-gate";

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  return <ProjectGate>{children}</ProjectGate>;
}
