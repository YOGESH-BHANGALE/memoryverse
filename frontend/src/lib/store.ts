/**
 * MemoryVerse AI — Global state store (Zustand).
 *
 * Manages:
 * - User identity / profile
 * - Upload state + results
 * - Timeline data
 * - Search state + streaming
 */

import { create } from "zustand";
import type {
  UserProfile,
  IngestionResult,
  TimelineResponse,
  RAGAnswerResponse,
  SourceAttribution,
  EntityCategory,
  CategorisedEntity,
} from "./types";
import {
  getUserProfile,
  uploadFile,
  uploadLink,
  getTimeline,
  ragQuery,
  ragQueryStream,
} from "./api";
import type { RAGQueryRequest } from "./types";

// ── Store Shape ────────────────────────────────────────────────────────

interface AppState {
  // Identity
  userId: string;
  profile: UserProfile | null;
  profileLoading: boolean;
  profileError: string | null;
  fetchProfile: () => Promise<void>;
  setUserId: (id: string) => void;

  // Upload
  uploadResult: IngestionResult | null;
  uploadLoading: boolean;
  uploadProgress: string;
  uploadError: string | null;
  doUpload: (file: File) => Promise<void>;
  doLinkUpload: (url: string) => Promise<void>;
  clearUpload: () => void;

  // Timeline
  timeline: TimelineResponse | null;
  timelineLoading: boolean;
  timelineError: string | null;
  fetchTimeline: (year?: string, category?: string) => Promise<void>;

  // Search
  searchResult: RAGAnswerResponse | null;
  streamingAnswer: string;
  streamingSources: SourceAttribution[];
  isStreaming: boolean;
  searchLoading: boolean;
  searchError: string | null;
  chatHistory: { role: "user" | "ai"; content: string }[];
  doSearch: (query: string, category?: EntityCategory) => Promise<void>;
  doSearchStream: (query: string, category?: EntityCategory) => Promise<void>;
  clearSearch: () => void;
}

// ── Store Implementation ───────────────────────────────────────────────

export const useAppStore = create<AppState>((set, get) => ({
  // ── Identity ─────────────────────────────────────────────────────────
  userId: "default",
  profile: null,
  profileLoading: false,
  profileError: null,

  setUserId: (id: string) => set({ userId: id }),

  fetchProfile: async () => {
    set({ profileLoading: true, profileError: null });
    try {
      const profile = await getUserProfile(get().userId);
      set({ profile, profileLoading: false });
    } catch (err: any) {
      set({
        profileError:
          err?.response?.data?.detail || "No data yet — upload a document first!",
        profileLoading: false,
      });
    }
  },

  // ── Upload ───────────────────────────────────────────────────────────
  uploadResult: null,
  uploadLoading: false,
  uploadProgress: "",
  uploadError: null,

  doUpload: async (file: File) => {
    set({
      uploadLoading: true,
      uploadProgress: "Uploading…",
      uploadError: null,
      uploadResult: null,
    });
    try {
      set({ uploadProgress: "Processing with AI…" });
      const result = await uploadFile(file, get().userId);
      set({ uploadResult: result, uploadLoading: false, uploadProgress: "Done" });
      // Refresh profile after upload
      get().fetchProfile();
    } catch (err: any) {
      set({
        uploadError:
          err?.response?.data?.detail || err.message || "Upload failed",
        uploadLoading: false,
        uploadProgress: "",
      });
    }
  },

  doLinkUpload: async (url: string) => {
    set({
      uploadLoading: true,
      uploadProgress: "Fetching link…",
      uploadError: null,
      uploadResult: null,
    });
    try {
      set({ uploadProgress: "Processing with AI…" });
      const result = await uploadLink(url, get().userId);
      set({ uploadResult: result, uploadLoading: false, uploadProgress: "Done" });
      get().fetchProfile();
    } catch (err: any) {
      set({
        uploadError:
          err?.response?.data?.detail || err.message || "Link processing failed",
        uploadLoading: false,
        uploadProgress: "",
      });
    }
  },

  clearUpload: () =>
    set({ uploadResult: null, uploadError: null, uploadProgress: "" }),

  // ── Timeline ─────────────────────────────────────────────────────────
  timeline: null,
  timelineLoading: false,
  timelineError: null,

  fetchTimeline: async (year?: string, category?: string) => {
    set({ timelineLoading: true, timelineError: null });
    try {
      const timeline = await getTimeline(get().userId, year, category);
      set({ timeline, timelineLoading: false });
    } catch (err: any) {
      set({
        timelineError:
          err?.response?.data?.detail || err.message || "Failed to load timeline",
        timelineLoading: false,
      });
    }
  },

  // ── Search ───────────────────────────────────────────────────────────
  searchResult: null,
  streamingAnswer: "",
  streamingSources: [],
  isStreaming: false,
  searchLoading: false,
  searchError: null,
  chatHistory: [],

  doSearch: async (query: string, category?: EntityCategory) => {
    const history = get().chatHistory;
    set({
      searchLoading: true,
      searchError: null,
      searchResult: null,
      streamingAnswer: "",
      streamingSources: [],
      chatHistory: [...history, { role: "user", content: query }],
    });
    try {
      const request: RAGQueryRequest = {
        query,
        user_id: get().userId,
        top_k: 10,
        category,
        use_mmr: true,
      };
      const result = await ragQuery(request);
      set({
        searchResult: result,
        searchLoading: false,
        chatHistory: [
          ...get().chatHistory,
          { role: "ai", content: result.answer },
        ],
      });
    } catch (err: any) {
      set({
        searchError: err?.response?.data?.detail || err.message || "Search failed",
        searchLoading: false,
      });
    }
  },

  doSearchStream: async (query: string, category?: EntityCategory) => {
    const history = get().chatHistory;
    set({
      searchLoading: true,
      isStreaming: true,
      searchError: null,
      searchResult: null,
      streamingAnswer: "",
      streamingSources: [],
      chatHistory: [...history, { role: "user", content: query }],
    });
    try {
      const request: RAGQueryRequest = {
        query,
        user_id: get().userId,
        top_k: 10,
        category,
        use_mmr: true,
        stream: true,
      };
      await ragQueryStream(request, {
        onChunk: (token: string) => {
          set((state) => ({
            streamingAnswer: state.streamingAnswer + token,
          }));
        },
        onSources: (sources: SourceAttribution[]) => {
          set({ streamingSources: sources });
        },
        onDone: () => {
          const finalAnswer = get().streamingAnswer;
          set({
            isStreaming: false,
            searchLoading: false,
            chatHistory: [
              ...get().chatHistory,
              { role: "ai", content: finalAnswer },
            ],
          });
        },
        onError: (errMsg: string) => {
          set({
            searchError: errMsg,
            isStreaming: false,
            searchLoading: false,
          });
        },
      });
    } catch (err: any) {
      set({
        searchError: err.message || "Streaming search failed",
        isStreaming: false,
        searchLoading: false,
      });
    }
  },

  clearSearch: () =>
    set({
      searchResult: null,
      streamingAnswer: "",
      streamingSources: [],
      searchError: null,
      chatHistory: [],
    }),
}));
