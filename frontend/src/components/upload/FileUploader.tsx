"use client";

import React, { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useAppStore } from "@/lib/store";

export const FileUploader: React.FC = () => {
  const {
    uploadResult,
    uploadLoading,
    uploadProgress,
    uploadError,
    doUpload,
    doLinkUpload,
    clearUpload,
  } = useAppStore();

  const [linkUrl, setLinkUrl] = React.useState("");

  const onDropRejected = useCallback(
    (fileRejections: any[]) => {
      const { errors } = fileRejections[0];
      let msg = "Invalid file";
      if (errors[0]?.code === "file-too-large") {
        msg = "File is too large (Max 50 MB)";
      } else if (errors[0]?.code === "file-invalid-type") {
        msg = "Unsupported file format";
      }
      useAppStore.setState({ uploadError: msg, uploadLoading: false });
    },
    []
  );

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) {
        useAppStore.setState({ uploadError: null });
        doUpload(accepted[0]);
      }
    },
    [doUpload]
  );

  const { getRootProps, getInputProps, isDragActive, acceptedFiles } =
    useDropzone({
      onDrop,
      onDropRejected,
      accept: {
        "application/pdf": [".pdf"],
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
          [".docx"],
        "text/plain": [".txt"],
      },
      maxSize: 50 * 1024 * 1024,
      maxFiles: 1,
      disabled: uploadLoading,
    });

  const currentFile = acceptedFiles[0] || null;

  return (
    <div className="space-y-6">
      {/* Drop zone */}
      <div {...getRootProps()}>
        <input {...getInputProps()} />
        <motion.div
          animate={{
            scale: isDragActive ? 1.02 : 1,
            borderColor: isDragActive ? "#5c7cfa" : "#373a4080",
          }}
          transition={{ duration: 0.2 }}
        >
          <Card
            className={`relative cursor-pointer transition-all duration-300 ${
              isDragActive
                ? "border-primary-500 bg-primary-500/5"
                : "hover:border-dark-300"
            } ${uploadLoading ? "pointer-events-none opacity-70" : ""}`}
          >
            <div className="flex flex-col items-center justify-center py-14">
              <motion.div
                animate={{
                  y: isDragActive ? -8 : 0,
                  scale: isDragActive ? 1.1 : 1,
                }}
                className="w-16 h-16 rounded-2xl bg-primary-500/10 flex items-center justify-center mb-4"
              >
                <svg
                  className="w-8 h-8 text-primary-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
              </motion.div>

              <p className="text-lg font-semibold text-white mb-1">
                {isDragActive
                  ? "Drop it here!"
                  : "Drag & drop your document"}
              </p>
              <p className="text-sm text-dark-200 mb-2">
                or click to browse • PDF, DOCX, TXT supported
              </p>
              <p className="text-xs text-dark-400">Max 50 MB</p>
            </div>
          </Card>
        </motion.div>
      </div>

      <div className="flex items-center gap-4">
        <div className="h-px bg-dark-600 flex-1" />
        <span className="text-dark-300 text-sm font-medium">OR PASTE A LINK</span>
        <div className="h-px bg-dark-600 flex-1" />
      </div>

      <div className="flex gap-3">
        <input
          type="url"
          placeholder="https://github.com/username/repo, linkedin, portfolio..."
          value={linkUrl}
          onChange={(e) => setLinkUrl(e.target.value)}
          disabled={uploadLoading}
          className="flex-1 rounded-xl bg-dark-700/50 border border-dark-400/30 px-4 py-2 text-sm text-white placeholder-dark-400 focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500 transition-all disabled:opacity-50"
        />
        <Button 
          disabled={uploadLoading || !linkUrl.trim()} 
          onClick={() => {
            if (linkUrl.trim()) doLinkUpload(linkUrl);
          }}
        >
          Process Link
        </Button>
      </div>

      {/* Selected file info */}
      <AnimatePresence>
        {currentFile && !uploadResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
          >
            <Card className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">📄</span>
                <div>
                  <p className="text-sm font-medium text-white">
                    {currentFile.name}
                  </p>
                  <p className="text-xs text-dark-300">
                    {(currentFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              </div>
              {!uploadLoading && (
                <Button onClick={() => doUpload(currentFile)} size="md">
                  Upload & Extract
                </Button>
              )}
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Progress bar */}
      <AnimatePresence>
        {uploadLoading && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            <Card>
              <div className="flex items-center gap-4">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-white">
                    {uploadProgress}
                  </p>
                  <div className="mt-2 h-1.5 bg-dark-600 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full"
                      initial={{ width: "5%" }}
                      animate={{ width: "85%" }}
                      transition={{ duration: 8, ease: "easeOut" }}
                    />
                  </div>
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error */}
      <AnimatePresence>
        {uploadError && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <Card className="border-red-500/30 bg-red-500/5">
              <div className="flex items-center justify-between">
                <p className="text-red-400 text-sm">❌ {uploadError}</p>
                <Button variant="ghost" size="sm" onClick={clearUpload}>
                  Dismiss
                </Button>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Result */}
      <AnimatePresence>
        {uploadResult && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          >
            <Card glow>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">
                  ✅ Extraction Complete
                </h3>
                <Button variant="ghost" size="sm" onClick={clearUpload}>
                  Clear
                </Button>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                <div className="bg-dark-600/50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-primary-400">
                    {uploadResult.entities_extracted}
                  </p>
                  <p className="text-xs text-dark-300">Entities</p>
                </div>
                <div className="bg-dark-600/50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-emerald-400">
                    {uploadResult.status === "completed" ? "✓" : "…"}
                  </p>
                  <p className="text-xs text-dark-300">Status</p>
                </div>
                <div className="bg-dark-600/50 rounded-lg p-3 text-center">
                  <p className="text-sm font-medium text-white truncate">
                    {uploadResult.filename}
                  </p>
                  <p className="text-xs text-dark-300">File</p>
                </div>
                <div className="bg-dark-600/50 rounded-lg p-3 text-center">
                  <p className="text-xs font-mono text-dark-200">
                    {uploadResult.job_id.slice(0, 8)}…
                  </p>
                  <p className="text-xs text-dark-300">Job ID</p>
                </div>
              </div>

              {/* Extracted entities */}
              {uploadResult.entities.length > 0 && (
                <div className="space-y-1.5 max-h-64 overflow-y-auto">
                  {uploadResult.entities.map((entity, i) => (
                    <motion.div
                      key={entity.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="flex items-center justify-between px-3 py-2 rounded-lg bg-dark-600/30 hover:bg-dark-600/60 transition-colors"
                    >
                      <span className="text-sm text-white">{entity.title}</span>
                      <div className="flex items-center gap-2">
                        <Badge category={entity.category} />
                        <span className="text-xs text-dark-400 font-mono">
                          ★{entity.importance_score}
                        </span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
