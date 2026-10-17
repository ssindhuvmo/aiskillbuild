import Card from "../components/Card.jsx";
import PageHeader from "../components/PageHeader.jsx";

// Placeholder for a sidebar page that is built in a later milestone (see SPEC.md).
export default function ComingSoon({ title, subtitle, milestone }) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <Card>
        <p>This page is not built yet. It arrives in milestone {milestone}.</p>
      </Card>
    </>
  );
}
