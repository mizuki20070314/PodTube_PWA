/* uinput_pad - a virtual keyboard-like pad for testing PodTube's evdev input on the M17 without touching it.
 *
 *   uinput_pad /tmp/pad.fifo        creates the device "pt-test-pad" and executes the commands written into the FIFO:
 *     d <code>   key down        u <code>   key up        t <code>   tap (down, 60 ms, up)
 *     a <code> <value>   absolute axis (0 = ABS_X, 1 = ABS_Y; 0..255, centre 128)
 *     w <ms>     wait            q          quit (destroys the device)
 *
 * build in the Alpine chroot:  gcc -static -O2 -o uinput_pad uinput_pad.c
 */
#include <fcntl.h>
#include <linux/uinput.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int fd;

static void emit(int type, int code, int value)
{
	struct input_event ev;
	memset(&ev, 0, sizeof ev);
	ev.type = type;
	ev.code = code;
	ev.value = value;
	if (write(fd, &ev, sizeof ev) < 0) perror("write");
}

static void key(int code, int down)
{
	emit(EV_KEY, code, down);
	emit(EV_SYN, SYN_REPORT, 0);
}

int main(int argc, char **argv)
{
	const char *path = argc > 1 ? argv[1] : "/tmp/pad.fifo";
	fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
	if (fd < 0) { perror("/dev/uinput"); return 1; }
	ioctl(fd, UI_SET_EVBIT, EV_KEY);
	ioctl(fd, UI_SET_EVBIT, EV_SYN);
	ioctl(fd, UI_SET_EVBIT, EV_ABS);
	ioctl(fd, UI_SET_ABSBIT, ABS_X);
	ioctl(fd, UI_SET_ABSBIT, ABS_Y);
	for (int c = 1; c < 250; c++) ioctl(fd, UI_SET_KEYBIT, c);
	struct uinput_user_dev uud;
	memset(&uud, 0, sizeof uud);
	snprintf(uud.name, UINPUT_MAX_NAME_SIZE, "%s", argc > 2 ? argv[2] : "pt-test-pad");
	uud.absmin[ABS_X] = uud.absmin[ABS_Y] = 0;
	uud.absmax[ABS_X] = uud.absmax[ABS_Y] = 255;
	uud.id.bustype = BUS_VIRTUAL;
	uud.id.vendor = 0x1234;
	uud.id.product = 0x5678;
	if (write(fd, &uud, sizeof uud) < 0) { perror("setup"); return 1; }
	if (ioctl(fd, UI_DEV_CREATE) < 0) { perror("create"); return 1; }
	unlink(path);
	mkfifo(path, 0666);
	fprintf(stderr, "pt-test-pad ready, commands via %s\n", path);
	char line[128];
	for (;;) {
		FILE *f = fopen(path, "r");
		if (!f) { sleep(1); continue; }
		while (fgets(line, sizeof line, f)) {
			char op;
			int v, v2 = 0;
			if (sscanf(line, " %c %d %d", &op, &v, &v2) < 1) continue;
			if (op == 'd') key(v, 1);
			else if (op == 'u') key(v, 0);
			else if (op == 't') { key(v, 1); usleep(60000); key(v, 0); }
			else if (op == 'a') { emit(EV_ABS, v, v2); emit(EV_SYN, SYN_REPORT, 0); }
			else if (op == 'w') usleep(v * 1000);
			else if (op == 'q') { ioctl(fd, UI_DEV_DESTROY); close(fd); return 0; }
		}
		fclose(f);
	}
}
