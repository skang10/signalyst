"use client";

import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";

export default function ResultsPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  useEffect(() => {
    router.replace(`/sessions/${id}/overview`);
  }, [id, router]);
  return null;
}
