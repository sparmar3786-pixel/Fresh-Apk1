import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:llama_flutter_android/llama_flutter_android.dart';
import 'package:path_provider/path_provider.dart';

/// Local-only Qwen GGUF chat. Model weights are downloaded once and stored in
/// app-private storage; prompts are sent directly to llama.cpp on this device.
class LocalQwenPage extends StatefulWidget {
  const LocalQwenPage({super.key});

  @override
  State<LocalQwenPage> createState() => _LocalQwenPageState();
}

class _LocalQwenPageState extends State<LocalQwenPage> {
  static const _modelFileName = 'Qwen3.5-4B-Q4_K_M.gguf';

  late LlamaController _controller;
  final _promptController = TextEditingController();
  final _scrollController = ScrollController();
  final List<_LocalMessage> _messages = [];
  String? _modelPath;
  String _status = 'Choose your existing GGUF model from Downloads';
  String? _error;
  bool _loading = false;
  bool _loaded = false;
  bool _generating = false;
  StreamSubscription<String>? _generation;

  @override
  void initState() {
    super.initState();
    _controller = LlamaController();
    _findExistingModel();
  }

  Future<File> _modelFile() async {
    final directory = await getApplicationSupportDirectory();
    final models = Directory('${directory.path}/models');
    if (!await models.exists()) await models.create(recursive: true);
    return File('${models.path}/$_modelFileName');
  }

  Future<void> _findExistingModel() async {
    try {
      final file = await _modelFile();
      if (!mounted) return;
      setState(() {
        _modelPath = file.path;
        _status = file.existsSync()
            ? 'GGUF file found • ready to load'
            : 'Select the existing GGUF file from Downloads';
      });
    } catch (e) {
      if (mounted) setState(() => _error = 'Storage check failed: $e');
    }
  }

  Future<bool> _hasGgufMagic(File file) async {
    if (!await file.exists() || await file.length() < 4) return false;
    final handle = await file.open(mode: FileMode.read);
    try {
      final header = await handle.read(4);
      return header.length == 4 &&
          header[0] == 0x47 &&
          header[1] == 0x47 &&
          header[2] == 0x55 &&
          header[3] == 0x46;
    } finally {
      await handle.close();
    }
  }

  Future<void> _pickExistingModel() async {
    if (_loading || _generating) return;
    setState(() {
      _error = null;
      _status = 'Choose Qwen3.5-4B-Q4_K_M.gguf from Downloads';
    });
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['gguf'],
        allowMultiple: false,
        withData: false,
      );
      if (result == null || result.files.isEmpty) return;
      final sourcePath = result.files.single.path;
      if (sourcePath == null || sourcePath.isEmpty) {
        throw const FormatException('Android did not provide a readable file path. Try copying the GGUF into Downloads and selecting it again.');
      }
      final source = File(sourcePath);
      if (!await source.exists() || !await _hasGgufMagic(source)) {
        throw const FormatException('Selected file is not a valid GGUF file.');
      }
      if (await source.length() < 1000000000) {
        throw const FormatException('The selected file looks too small for this 4B Q4_K_M model; check that the download is complete.');
      }
      final destination = await _modelFile();
      if (source.absolute.path != destination.absolute.path) {
        await source.copy(destination.path);
      }
      if (!mounted) return;
      setState(() {
        _modelPath = destination.path;
        _status = 'Existing model copied into app storage • ready to load';
      });
    } catch (e) {
      if (mounted) setState(() {
        _error = 'Could not import model: $e';
        _status = 'Model not ready';
      });
    }
  }

  Future<void> _loadModel() async {
    if (_loading || _loaded || _modelPath == null) return;
    final file = File(_modelPath!);
    if (!await file.exists() || await file.length() < 1000000000 ||
        !await _hasGgufMagic(file)) {
      setState(() => _error = 'Model file is missing or incomplete. Download it again.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _status = 'Loading model into memory…';
    });
    try {
      // Start with a conservative context to reduce memory pressure on phones.
      await _controller.loadModel(
        modelPath: file.path,
        threads: 4,
        contextSize: 2048,
      );
      if (!mounted) return;
      setState(() {
        _loaded = true;
        _status = 'Loaded • inference runs locally on this phone';
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Model load failed: $e. This build may not support this GGUF architecture or the phone may lack free RAM.';
          _status = 'Model not loaded';
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _sendPrompt() async {
    final prompt = _promptController.text.trim();
    if (!_loaded || _generating || prompt.isEmpty) return;
    _promptController.clear();
    final assistant = _LocalMessage(isUser: false, text: '');
    setState(() {
      _messages.add(_LocalMessage(isUser: true, text: prompt));
      _messages.add(assistant);
      _generating = true;
      _error = null;
      _status = 'Generating locally…';
    });
    _scrollToBottom();

    try {
      final history = _messages
          .where((message) => message.text.isNotEmpty)
          .toList();
      final chatMessages = <ChatMessage>[
        ChatMessage(
          role: 'system',
          content: 'You are Fresh Local Qwen, a concise assistant. For trading questions, use only facts supplied in the prompt, state uncertainty, and never invent live prices or claim an unverified trade is safe.',
        ),
        for (final message in history)
          ChatMessage(
            role: message.isUser ? 'user' : 'assistant',
            content: message.text,
          ),
      ];
      _generation = _controller
          .generateChat(
            messages: chatMessages,
            template: 'chatml',
            temperature: 0.6,
            topP: 0.95,
            topK: 20,
            maxTokens: 512,
          )
          .listen(
            (token) {
              if (!mounted) return;
              setState(() {
                assistant.text += token;
                _status = 'Generating locally…';
              });
              _scrollToBottom();
            },
            onError: (Object error) {
              if (mounted) setState(() => _error = 'Inference failed: $error');
            },
          );
      await _generation!.asFuture<void>();
      if (mounted) setState(() => _status = 'Ready • local inference');
    } catch (e) {
      if (mounted) setState(() => _error = 'Inference failed: $e');
    } finally {
      await _generation?.cancel();
      _generation = null;
      if (mounted) setState(() => _generating = false);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    unawaited(_generation?.cancel());
    _promptController.dispose();
    _scrollController.dispose();
    if (_loaded) unawaited(_controller.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canSelect = !_loading && !_generating;
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text(
          'LOCAL QWEN • OFFLINE AI',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        const Text(
          'Qwen3.5-4B GGUF • Q4_K_M • on-device inference',
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Icon(
                    _loaded ? Icons.verified : Icons.memory,
                    color: _loaded ? Colors.greenAccent : Colors.cyanAccent,
                  ),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_status)),
                ]),
                const SizedBox(height: 12),
                if (!_loaded)
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    OutlinedButton.icon(
                      onPressed: canSelect ? _pickExistingModel : null,
                      icon: const Icon(Icons.folder_open),
                      label: const Text('Select existing GGUF'),
                    ),
                    FilledButton.icon(
                      onPressed: canSelect &&
                              _modelPath != null &&
                              File(_modelPath!).existsSync()
                          ? _loadModel
                          : null,
                      icon: const Icon(Icons.memory),
                      label: const Text('Load model'),
                    ),
                  ]),
                if (_loaded)
                  OutlinedButton.icon(
                    onPressed: _generating
                        ? null
                        : () async {
                            await _controller.dispose();
                            if (mounted) {
                              setState(() {
                                _controller = LlamaController();
                                _loaded = false;
                                _status = 'Model unloaded';
                              });
                            }
                          },
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: const Text('Unload model'),
                  ),
                if (_error != null) ...[
                  const SizedBox(height: 10),
                  Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                ],
              ],
            ),
          ),
        ),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'The app reuses your existing GGUF file; no model download is started. It copies the selected file into app-private storage, then loads it with the bundled native engine. Chat can work offline after successful load. Live market data still requires a data connection. A 4B model may need several GB of free RAM; load failure can indicate RAM or model-format incompatibility.',
              style: TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(4, 16, 4, 8),
          child: Text('LOCAL CHAT', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
        ),
        Container(
          constraints: const BoxConstraints(minHeight: 180, maxHeight: 380),
          child: ListView.builder(
            controller: _scrollController,
            shrinkWrap: true,
            itemCount: _messages.length,
            itemBuilder: (context, index) {
              final message = _messages[index];
              return Align(
                alignment: message.isUser
                    ? Alignment.centerRight
                    : Alignment.centerLeft,
                child: Card(
                  color: message.isUser
                      ? const Color(0xFF123447)
                      : const Color(0xFF101722),
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: SelectableText(
                      message.text.isEmpty && _generating
                          ? 'Thinking…'
                          : message.text,
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 8),
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Expanded(
            child: TextField(
              controller: _promptController,
              minLines: 1,
              maxLines: 4,
              enabled: _loaded && !_generating,
              decoration: const InputDecoration(
                labelText: 'Ask local Qwen',
                hintText: 'No live prices unless you provide the data',
              ),
              onSubmitted: (_) => _sendPrompt(),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: _loaded && !_generating ? _sendPrompt : null,
            tooltip: 'Send prompt',
            icon: const Icon(Icons.send),
          ),
          if (_generating)
            IconButton(
              onPressed: () async {
                await _controller.stop();
                await _generation?.cancel();
                if (mounted) setState(() => _generating = false);
              },
              tooltip: 'Stop generation',
              icon: const Icon(Icons.stop),
            ),
        ]),
      ],
    );
  }
}

class _LocalMessage {
  _LocalMessage({required this.isUser, required this.text});
  final bool isUser;
  String text;
}
