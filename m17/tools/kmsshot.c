/* kmsshot - 今 KMS(DRM) が画面に出しているバッファ(全プレーン)を生ピクセルで書き出す。
 *
 * M17 の MinUI も LÖVE(SDL2 kmsdrm+Mali)も DRM で描くので、/dev/fb0 には何も出ない。
 * 実際に走査されているフレームバッファを DRM の ioctl で直接読む(libdrm 不要・静的リンク可)。
 *
 *   kmsshot [出力プレフィックス]     既定 /tmp/kms
 *   -> /tmp/kms_plane<ID>.raw と、標準出力に1プレーン1行:
 *      plane=<id> crtc=<id> fb=<id> w=<W> h=<H> pitch=<P> bpp=<B> depth=<D> file=<path>
 *
 * ビルド(端末の Alpine chroot): gcc -static -O2 -o kmsshot kmsshot.c
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>

static int xioctl(int fd, unsigned long req, void *arg)
{
	int r;
	do { r = ioctl(fd, req, arg); } while (r < 0 && (errno == EINTR || errno == EAGAIN));
	return r;
}

static int dump_fb(int fd, uint32_t plane, uint32_t crtc, uint32_t fb, const char *prefix)
{
	struct drm_mode_fb_cmd f;
	memset(&f, 0, sizeof f);
	f.fb_id = fb;
	if (xioctl(fd, DRM_IOCTL_MODE_GETFB, &f) < 0) {
		fprintf(stderr, "GETFB(%u): %s\n", fb, strerror(errno));
		return -1;
	}
	size_t len = (size_t)f.pitch * f.height;
	void *map = MAP_FAILED;
	const char *how = "dumb";

	struct drm_mode_map_dumb md;
	memset(&md, 0, sizeof md);
	md.handle = f.handle;
	if (xioctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &md) == 0)
		map = mmap(NULL, len, PROT_READ, MAP_SHARED, fd, (off_t)md.offset);
	if (map == MAP_FAILED) {
		struct drm_prime_handle ph;
		memset(&ph, 0, sizeof ph);
		ph.handle = f.handle;
		ph.flags = DRM_CLOEXEC | DRM_RDWR;
		if (xioctl(fd, DRM_IOCTL_PRIME_HANDLE_TO_FD, &ph) == 0) {
			map = mmap(NULL, len, PROT_READ, MAP_SHARED, ph.fd, 0);
			how = "prime";
			close(ph.fd);
		}
	}
	if (map == MAP_FAILED) {
		fprintf(stderr, "mmap fb %u failed: %s\n", fb, strerror(errno));
		return -1;
	}
	char path[256];
	snprintf(path, sizeof path, "%s_plane%u.raw", prefix, plane);
	FILE *o = fopen(path, "wb");
	if (!o) { perror(path); munmap(map, len); return -1; }
	fwrite(map, 1, len, o);
	fclose(o);
	munmap(map, len);
	printf("plane=%u crtc=%u fb=%u w=%u h=%u pitch=%u bpp=%u depth=%u how=%s file=%s\n",
	       plane, crtc, fb, f.width, f.height, f.pitch, f.bpp, f.depth, how, path);
	return 0;
}

int main(int argc, char **argv)
{
	const char *prefix = argc > 1 ? argv[1] : "/tmp/kms";
	const char *dev = getenv("KMS_DEV") ? getenv("KMS_DEV") : "/dev/dri/card0";
	int fd = open(dev, O_RDWR | O_CLOEXEC);
	if (fd < 0) { perror(dev); return 2; }

	struct drm_set_client_cap cap = { DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1 };
	xioctl(fd, DRM_IOCTL_SET_CLIENT_CAP, &cap);

	struct drm_mode_get_plane_res pr;
	memset(&pr, 0, sizeof pr);
	if (xioctl(fd, DRM_IOCTL_MODE_GETPLANERESOURCES, &pr) < 0) { perror("GETPLANERESOURCES"); return 3; }
	uint32_t *ids = calloc(pr.count_planes + 1, sizeof *ids);
	pr.plane_id_ptr = (uint64_t)(uintptr_t)ids;
	if (xioctl(fd, DRM_IOCTL_MODE_GETPLANERESOURCES, &pr) < 0) { perror("GETPLANERESOURCES2"); return 3; }

	int shown = 0;
	for (uint32_t i = 0; i < pr.count_planes; i++) {
		struct drm_mode_get_plane gp;
		memset(&gp, 0, sizeof gp);
		gp.plane_id = ids[i];
		if (xioctl(fd, DRM_IOCTL_MODE_GETPLANE, &gp) < 0) continue;
		if (gp.fb_id == 0) { printf("plane=%u idle\n", ids[i]); continue; }
		if (dump_fb(fd, ids[i], gp.crtc_id, gp.fb_id, prefix) == 0) shown++;
	}
	if (!shown) {
		/* universal planes が使えない場合の保険: CRTC の fb_id を見る */
		struct drm_mode_card_res cr;
		memset(&cr, 0, sizeof cr);
		xioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &cr);
		uint32_t *crt = calloc(cr.count_crtcs + 1, sizeof *crt);
		cr.crtc_id_ptr = (uint64_t)(uintptr_t)crt;
		cr.count_fbs = cr.count_connectors = cr.count_encoders = 0;
		if (xioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &cr) == 0) {
			for (uint32_t i = 0; i < cr.count_crtcs; i++) {
				struct drm_mode_crtc c;
				memset(&c, 0, sizeof c);
				c.crtc_id = crt[i];
				if (xioctl(fd, DRM_IOCTL_MODE_GETCRTC, &c) == 0 && c.fb_id)
					if (dump_fb(fd, 0, c.crtc_id, c.fb_id, prefix) == 0) shown++;
			}
		}
	}
	return shown ? 0 : 1;
}
