import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TabMetrics } from "@/components/evals/TabMetrics";
import { TabFailures } from "@/components/evals/TabFailures";
import { TabExperiments } from "@/components/evals/TabExperiments";
import { TabLiveDemo } from "@/components/evals/TabLiveDemo";

export const metadata = {
  title: "Evals — Clauseline",
};

export default function EvalsPage() {
  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Evals</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Metrics, failures, experiments, and live demo. The system is only as good as what it admits it gets wrong.
        </p>
      </div>

      <Tabs defaultValue="metrics">
        <TabsList className="mb-6">
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="failures">Failures</TabsTrigger>
          <TabsTrigger value="experiments">Experiments</TabsTrigger>
          <TabsTrigger value="demo">Live demo</TabsTrigger>
        </TabsList>

        <TabsContent value="metrics">
          <TabMetrics />
        </TabsContent>

        <TabsContent value="failures">
          <TabFailures />
        </TabsContent>

        <TabsContent value="experiments">
          <TabExperiments />
        </TabsContent>

        <TabsContent value="demo">
          <TabLiveDemo />
        </TabsContent>
      </Tabs>
    </main>
  );
}
